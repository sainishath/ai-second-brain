"""
api.py — FastAPI Server for AI Second Brain v2
Full endpoints: ingestion, chat, search, file upload, dashboard.
Run: python src/api.py
"""

import os
import sys
import re
import json
import shutil
import asyncio
import hashlib
import sqlite3
import yaml
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))

# Thread pool — blocks LLM/embedding calls off the event loop
_executor = ThreadPoolExecutor(max_workers=4)

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

from ingest import ingest as _ingest
from retriever import HybridRetriever
from generator import get_generator

_ROOT_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
_NOTES_DIR  = _ROOT_DIR / "data" / "notes"
_DRIVE_DIR  = _ROOT_DIR / "data" / "google_drive"
_BRIEFS_DIR = _ROOT_DIR / "data" / "briefs"
_RAW_DIR    = _ROOT_DIR / "data" / "raw"

# Concurrency control & background task
_indexing_in_progress: set[str] = set()

def run_indexing_task(filepath_str: str):
    try:
        from notes_processor import NotesProcessor
        processor = NotesProcessor()
        processor.process_note_file(Path(filepath_str))
    except Exception as e:
        print(f"[Index Task] Error processing {filepath_str}: {e}")
    finally:
        _indexing_in_progress.discard(filepath_str)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize and migrate SQLite tracking database on startup
    db_path = _ROOT_DIR / "data" / "metadata.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    
    # 1. Ensure notes_tracking table is created with full columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes_tracking (
            filepath TEXT PRIMARY KEY,
            last_modified REAL,
            file_hash TEXT,
            doc_id TEXT,
            themes TEXT,
            processed_at TEXT,
            source_url TEXT,
            is_archived INTEGER DEFAULT 0,
            tags TEXT
        )
    """)
    
    # 2. Add columns if missing for migrations
    cursor.execute("PRAGMA table_info(notes_tracking)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "source_url" not in columns:
        try:
            cursor.execute("ALTER TABLE notes_tracking ADD COLUMN source_url TEXT")
        except Exception as e:
            print(f"[Lifespan] Migration warning adding source_url: {e}")
    if "is_archived" not in columns:
        try:
            cursor.execute("ALTER TABLE notes_tracking ADD COLUMN is_archived INTEGER DEFAULT 0")
        except Exception as e:
            print(f"[Lifespan] Migration warning adding is_archived: {e}")
    if "tags" not in columns:
        try:
            cursor.execute("ALTER TABLE notes_tracking ADD COLUMN tags TEXT")
        except Exception as e:
            print(f"[Lifespan] Migration warning adding tags: {e}")
            
    conn.commit()
    conn.close()
    yield

# Ensure dirs exist
for d in [_NOTES_DIR, _DRIVE_DIR, _BRIEFS_DIR, _RAW_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── App ──────────────────────────────────────────────────────
app = FastAPI(title="AI Second Brain", version="2.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

retriever = HybridRetriever()
generator = get_generator()

# ─── Request Models ───────────────────────────────────────────
class IngestRequest(BaseModel):
    url: Optional[str] = None
    youtube: Optional[str] = None
    text: Optional[str] = None
    title: Optional[str] = ""

class ChatRequest(BaseModel):
    question: str
    n_results: int = 8
    history: Optional[List[dict]] = None

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5

class NoteRequest(BaseModel):
    name: str
    content: str
    type: str = "note"
    overwrite: bool = False
    tags: List[str] = []

class ImportRequest(BaseModel):
    url: str

# ─── File routing logic ───────────────────────────────────────
NOTE_EXTS  = {".md"}
DOC_EXTS   = {".pdf", ".docx", ".txt"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

def route_upload(filename: str) -> tuple[Path, str]:
    """Returns (destination_folder, category_label) based on file extension."""
    ext = Path(filename).suffix.lower()
    if ext in NOTE_EXTS:
        return _NOTES_DIR, "Notes Vault"
    elif ext in DOC_EXTS:
        return _DRIVE_DIR, "Documents"
    else:
        return _RAW_DIR, "Raw Files"

def auto_add_frontmatter(content: str, filename: str) -> str:
    """If a .md file has no frontmatter, prepend a minimal one."""
    if content.strip().startswith("---"):
        return content
    title = Path(filename).stem.replace("-", " ").replace("_", " ").title()
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    frontmatter = f"""---
type: note
created: {today}
tags: [imported]
status: raw
---

"""
    return frontmatter + content

# ─── Dashboard Helper Functions ───────────────────────────────
def parse_brief_sections(content: str) -> dict:
    sections = {"ingestion": [], "tasks": [], "connections": [], "research": [], "raw": content}
    current = None
    for line in content.splitlines():
        if "Ingestion" in line and "##" in line:       current = "ingestion"
        elif "Action Items" in line and "##" in line:  current = "tasks"
        elif "Concept Connections" in line and "##" in line: current = "connections"
        elif "Fact-Checking" in line and "##" in line: current = "research"

        if line.startswith("- [ ]") or line.startswith("- [x]") or line.startswith("- [X]"):
            m = re.match(r"- \[([ xX])\] (.+)", line)
            if m:
                sections["tasks"].append({"done": m.group(1).lower() == "x", "text": m.group(2).strip()})
        elif line.startswith("- ") and current and current != "tasks":
            text = line[2:].strip()
            if text and not text.startswith("*No "):
                sections[current].append(text)
    return sections

def get_all_notes() -> List[dict]:
    notes = []
    for path in sorted(_NOTES_DIR.glob("*.md")):
        if path.name in ["Daily Brief.md"]:
            continue
        try:
            content = path.read_text(encoding="utf-8")
            fm = {}
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    try:
                        fm = yaml.safe_load(content[3:end]) or {}
                    except Exception:
                        for l in content[3:end].splitlines():
                            if ":" in l:
                                k, _, v = l.partition(":")
                                fm[k.strip()] = v.strip()
            tags_raw = fm.get("tags", [])
            if isinstance(tags_raw, str):
                tags = re.findall(r"\w[\w-]*", tags_raw)
            elif isinstance(tags_raw, list):
                tags = [str(t) for t in tags_raw]
            else:
                tags = []
            word_count = len(re.sub(r"[^a-zA-Z ]", " ", content).split())
            links = list(set(re.findall(r"\[\[([^\]]+)\]\]", content)))
            has_ai = "## 🤖 AI Summary" in content
            
            is_archived_val = False
            archived_raw = fm.get("archived")
            if archived_raw is not None:
                if isinstance(archived_raw, str):
                    is_archived_val = archived_raw.lower() == "true"
                else:
                    is_archived_val = bool(archived_raw)

            notes.append({
                "name": path.stem, "filename": path.name,
                "type": fm.get("type", "note"), "created": fm.get("created", ""),
                "tags": tags, "word_count": word_count, "links": links,
                "has_ai_insights": has_ai, "status": fm.get("status", ""),
                "preview": re.sub(r"\s+", " ", re.sub(r"---.*?---", "", content, flags=re.DOTALL).strip()[:200]),
                "archived": is_archived_val
            })
        except Exception:
            pass
    return notes

def get_latest_brief() -> dict:
    briefs = sorted(_BRIEFS_DIR.glob("Daily Brief *.md"), reverse=True)
    if not briefs:
        return {"found": False}
    content = briefs[0].read_text(encoding="utf-8")
    sections = parse_brief_sections(content)
    sections.update({"found": True, "filename": briefs[0].name,
                     "date": briefs[0].stem.replace("Daily Brief ", "")})
    return sections

def get_index_categories() -> dict:
    index_path = _NOTES_DIR / "index.md"
    if not index_path.exists():
        return {}
    content = index_path.read_text(encoding="utf-8")
    categories, current_cat = {}, None
    for line in content.splitlines():
        m_cat  = re.match(r"^###\s+(.+)", line)
        m_link = re.match(r"^\s+-\s+\[\[([^\]]+)\]\]", line)
        if m_cat:
            current_cat = m_cat.group(1).strip()
            categories[current_cat] = []
        elif m_link and current_cat:
            categories[current_cat].append(m_link.group(1).strip())
    return categories

# ─── Routes ───────────────────────────────────────────────────

@app.get("/")
def root():
    landing_path = _ROOT_DIR / "src" / "landing.html"
    if landing_path.exists():
        return HTMLResponse(landing_path.read_text(encoding="utf-8"))
    dashboard_path = _ROOT_DIR / "src" / "dashboard.html"
    if dashboard_path.exists():
        return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))
    return {"name": "AI Second Brain", "status": "running"}

@app.get("/dashboard")
def dashboard():
    dashboard_path = _ROOT_DIR / "src" / "dashboard.html"
    if dashboard_path.exists():
        return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard Not Found</h1>", status_code=404)

@app.get("/api/overview")
async def overview_endpoint():
    loop = asyncio.get_event_loop()
    notes = await loop.run_in_executor(_executor, get_all_notes)
    brief = get_latest_brief()
    categories = get_index_categories()
    db_stats = await loop.run_in_executor(_executor, retriever.stats)
    total_tasks = len([t for t in brief.get("tasks", []) if isinstance(t, dict)])
    done_tasks  = len([t for t in brief.get("tasks", []) if isinstance(t, dict) and t.get("done")])
    return {
        "total_notes": len(notes),
        "total_chunks": db_stats.get("total_chunks", 0),
        "total_categories": len([k for k,v in categories.items() if v]),
        "total_links": sum(len(n["links"]) for n in notes),
        "total_tasks": total_tasks, "done_tasks": done_tasks,
        "notes_with_ai": len([n for n in notes if n["has_ai_insights"]]),
        "last_brief_date": brief.get("date", "Never"),
        "categories": categories,
    }

@app.get("/api/brief")
async def brief_endpoint():
    return get_latest_brief()

@app.get("/api/notes")
async def notes_endpoint():
    loop = asyncio.get_event_loop()
    notes = await loop.run_in_executor(_executor, get_all_notes)
    return {"notes": notes}

def sanitize_import_filename(title: str) -> str:
    # Strip characters outside [a-zA-Z0-9_-], replace spaces with _
    title = title.replace(" ", "_")
    title = re.sub(r"[^a-zA-Z0-9_\-]", "", title)
    title = title.lower()
    title = title[:50]
    return f"{title}_imported"

def get_active_notes_with_content() -> List[dict]:
    notes = []
    for path in sorted(_NOTES_DIR.glob("*.md")):
        if path.name in ["Daily Brief.md", "index.md"]:
            continue
        try:
            content = path.read_text(encoding="utf-8")
            fm = {}
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    try:
                        fm = yaml.safe_load(content[3:end]) or {}
                    except Exception:
                        pass
            
            is_archived = fm.get("archived", False)
            if isinstance(is_archived, str):
                is_archived = is_archived.lower() == "true"
            if is_archived:
                continue
                
            tags_raw = fm.get("tags", [])
            if isinstance(tags_raw, str):
                tags = re.findall(r"\w[\w-]*", tags_raw)
            elif isinstance(tags_raw, list):
                tags = [str(t) for t in tags_raw]
            else:
                tags = []
                
            notes.append({
                "name": path.stem,
                "type": fm.get("type", "note"),
                "tags": tags,
                "content": content,
                "last_modified": path.stat().st_mtime
            })
        except Exception:
            pass
    return notes

@app.get("/api/note/{name}")
async def note_detail(name: str):
    path = _NOTES_DIR / f"{name}.md"
    if not path.exists():
        raise HTTPException(404, "Note not found")
    return {"name": name, "content": path.read_text(encoding="utf-8")}

@app.post("/api/note")
async def create_or_update_note(req: NoteRequest, background_tasks: BackgroundTasks):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Note name cannot be empty")
        
    filename = f"{name}.md"
    filepath = _NOTES_DIR / filename
    
    # Handle name collision if not overwrite
    if not req.overwrite and filepath.exists():
        counter = 2
        while True:
            new_stem = f"{name}_{counter}"
            filepath = _NOTES_DIR / f"{new_stem}.md"
            if not filepath.exists():
                name = new_stem
                filename = f"{name}.md"
                break
            counter += 1
            
    # Process content and extract/merge frontmatter
    content = req.content
    clean_content = re.sub(r'^---\r?\n[\s\S]*?\r?\n---\r?\n?', '', content)
    
    # Initialize basic frontmatter
    fm = {
        "type": req.type,
        "status": "raw",
        "archived": False,
        "tags": req.tags,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Merge existing frontmatter keys if they were present
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", content)
    if match:
        try:
            existing_fm = yaml.safe_load(match.group(1))
            if isinstance(existing_fm, dict):
                fm.update(existing_fm)
                fm["type"] = req.type
                fm["status"] = "raw"
                fm["archived"] = False
                fm["tags"] = req.tags
        except Exception:
            pass
            
    fm_yaml = yaml.dump(fm, default_flow_style=False).strip()
    clean_content = clean_content.replace("\r\n", "\n")
    final_content = f"---\n{fm_yaml}\n---\n\n{clean_content.lstrip()}"
    
    try:
        filepath.write_text(final_content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write note: {e}")
        
    content_hash = hashlib.md5(final_content.encode("utf-8")).hexdigest()
    
    db_path = _ROOT_DIR / "data" / "metadata.db"
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT file_hash FROM notes_tracking WHERE filepath = ?", (str(filepath),))
    row = cursor.fetchone()
    conn.close()
    
    hash_changed = True
    if row and row[0] == content_hash:
        hash_changed = False
        
    filepath_str = str(filepath)
    if hash_changed and filepath_str not in _indexing_in_progress:
        _indexing_in_progress.add(filepath_str)
        background_tasks.add_task(run_indexing_task, filepath_str)
        
    return {"status": "ok", "name": name}

@app.get("/api/note/{name}/status")
async def note_status(name: str):
    filepath = _NOTES_DIR / f"{name}.md"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Note not found")
        
    try:
        content = filepath.read_text(encoding="utf-8")
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read note file: {e}")
        
    db_path = _ROOT_DIR / "data" / "metadata.db"
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT file_hash FROM notes_tracking WHERE filepath = ?", (str(filepath),))
    row = cursor.fetchone()
    conn.close()
    
    is_indexing = str(filepath) in _indexing_in_progress or not row or row[0] != content_hash
    
    if is_indexing:
        return {"status": "indexing"}
    else:
        return {"status": "indexed"}

@app.get("/api/tags")
async def get_tags():
    db_path = _ROOT_DIR / "data" / "metadata.db"
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM notes_tracking WHERE is_archived = 0")
    rows = cursor.fetchall()
    conn.close()
    
    all_tags = []
    for (tags_str,) in rows:
        if tags_str:
            all_tags.extend(tags_str.split(","))
    return sorted(set(t.strip() for t in all_tags if t.strip()))

@app.delete("/api/note/{name}")
async def delete_note(name: str, hard: bool = False):
    filepath = _NOTES_DIR / f"{name}.md"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Note not found")
        
    db_path = _ROOT_DIR / "data" / "metadata.db"
    
    if not hard:
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
            
        fm = {}
        clean_content = content
        match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", content)
        if match:
            try:
                fm = yaml.safe_load(match.group(1)) or {}
                clean_content = re.sub(r'^---\r?\n[\s\S]*?\r?\n---\r?\n?', '', content)
            except Exception:
                pass
                
        fm["archived"] = True
        fm_yaml = yaml.dump(fm, default_flow_style=False).strip()
        final_content = f"---\n{fm_yaml}\n---\n\n{clean_content.lstrip()}"
        
        try:
            filepath.write_text(final_content, encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write note: {e}")
            
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("UPDATE notes_tracking SET is_archived = 1 WHERE filepath = ?", (str(filepath),))
        conn.commit()
        conn.close()
        
        return {"status": "archived"}
    else:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("SELECT doc_id FROM notes_tracking WHERE filepath = ?", (str(filepath),))
        row = cursor.fetchone()
        doc_id = row[0] if row else None
        
        cursor.execute("DELETE FROM notes_tracking WHERE filepath = ?", (str(filepath),))
        if doc_id:
            cursor.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        conn.commit()
        conn.close()
        
        try:
            filepath.unlink()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
            
        if doc_id:
            try:
                retriever.collection.delete(where={"doc_id": doc_id})
            except Exception as e:
                print(f"[Delete Note] ChromaDB purge warning: {e}")
                
        return {"status": "deleted"}

@app.post("/api/note/{name}/restore")
async def restore_note(name: str, background_tasks: BackgroundTasks):
    filepath = _NOTES_DIR / f"{name}.md"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Note not found")
        
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
        
    fm = {}
    clean_content = content
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", content)
    if match:
        try:
            fm = yaml.safe_load(match.group(1)) or {}
            clean_content = re.sub(r'^---\r?\n[\s\S]*?\r?\n---\r?\n?', '', content)
        except Exception:
            pass
            
    fm["archived"] = False
    
    db_path = _ROOT_DIR / "data" / "metadata.db"
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT file_hash, doc_id FROM notes_tracking WHERE filepath = ?", (str(filepath),))
    row = cursor.fetchone()
    
    skip_indexing = False
    if row and row[0]:
        existing_hash = row[0]
        
        # We test both "indexed" and "processed" status values, and both with/without "archived" key
        # to ensure robust, backward-compatible matching of unmodified file contents.
        fm_clean = fm.copy()
        fm_clean.pop("archived", None)
        
        match_found = False
        for status in ["indexed", "processed"]:
            for with_archived in [True, False]:
                fm_test = fm_clean.copy()
                fm_test["status"] = status
                if with_archived:
                    fm_test["archived"] = False
                
                fm_yaml_test = yaml.dump(fm_test, default_flow_style=False).strip()
                reconstructed_content = f"---\n{fm_yaml_test}\n---\n\n{clean_content.lstrip()}"
                test_hash = hashlib.md5(reconstructed_content.encode("utf-8")).hexdigest()
                if test_hash == existing_hash:
                    match_found = True
                    break
            if match_found:
                break
                
        if match_found:
            skip_indexing = True
            
    if skip_indexing:
        fm["status"] = "indexed"
        fm_yaml = yaml.dump(fm, default_flow_style=False).strip()
        final_content = f"---\n{fm_yaml}\n---\n\n{clean_content.lstrip()}"
        filepath.write_text(final_content, encoding="utf-8")
        new_hash = hashlib.md5(final_content.encode("utf-8")).hexdigest()
        
        cursor.execute("UPDATE notes_tracking SET is_archived = 0, file_hash = ? WHERE filepath = ?", (new_hash, str(filepath)))
        conn.commit()
        conn.close()
        return {"status": "restored", "indexed": True}
    else:
        fm["status"] = "raw"
        fm_yaml = yaml.dump(fm, default_flow_style=False).strip()
        final_content = f"---\n{fm_yaml}\n---\n\n{clean_content.lstrip()}"
        filepath.write_text(final_content, encoding="utf-8")
        
        cursor.execute("UPDATE notes_tracking SET is_archived = 0 WHERE filepath = ?", (str(filepath),))
        conn.commit()
        conn.close()
        
        filepath_str = str(filepath)
        if filepath_str not in _indexing_in_progress:
            _indexing_in_progress.add(filepath_str)
            background_tasks.add_task(run_indexing_task, filepath_str)
            
        return {"status": "restored", "indexed": False}

@app.post("/api/import")
async def import_url(req: ImportRequest, background_tasks: BackgroundTasks):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
        
    db_path = _ROOT_DIR / "data" / "metadata.db"
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT filepath, is_archived FROM notes_tracking WHERE source_url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        existing_path = Path(row[0])
        if existing_path.exists():
            return {"status": "exists", "name": existing_path.stem}
            
    from ingest import load_url
    try:
        doc = load_url(url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bad Gateway: Failed to fetch/parse URL: {e}")
        
    title = doc.title or "Imported Note"
    sanitized_title = sanitize_import_filename(title)
    
    filepath = _NOTES_DIR / f"{sanitized_title}.md"
    if filepath.exists():
        counter = 2
        while True:
            new_title = f"{sanitized_title}_{counter}"
            filepath = _NOTES_DIR / f"{new_title}.md"
            if not filepath.exists():
                sanitized_title = new_title
                break
            counter += 1
            
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fm = {
        "type": "imported",
        "status": "raw",
        "archived": False,
        "tags": ["imported"],
        "created": today,
        "source_url": url,
        "title": title
    }
    
    fm_yaml = yaml.dump(fm, default_flow_style=False).strip()
    body_content = doc.content.replace("\r\n", "\n")
    final_content = f"---\n{fm_yaml}\n---\n\n{body_content}"
    
    try:
        filepath.write_text(final_content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write note: {e}")
        
    filepath_str = str(filepath)
    if filepath_str not in _indexing_in_progress:
        _indexing_in_progress.add(filepath_str)
        background_tasks.add_task(run_indexing_task, filepath_str)
        
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO notes_tracking (filepath, last_modified, file_hash, doc_id, themes, processed_at, source_url, is_archived, tags)
        VALUES (?, 0.0, '', '', '', '', ?, 0, 'imported')
    """, (filepath_str, url))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "name": sanitized_title}

@app.get("/api/notes/graph")
async def notes_graph(query: Optional[str] = None):
    active_notes = get_active_notes_with_content()
    if not active_notes:
        return {"nodes": [], "links": []}
        
    active_notes_map = {n["name"]: n for n in active_notes}
    
    # Extract wikilinks from each active note
    WIKILINK_RE = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    for note in active_notes:
        links = WIKILINK_RE.findall(note["content"])
        note["wikilinks"] = {lnk.strip() for lnk in links if lnk.strip() and lnk.strip() != note["name"]}
        
    matched_names = set()
    if query:
        query_lower = query.lower()
        # Semantic search
        try:
            hits = retriever.retrieve(query, n=200)
            for h in hits:
                meta = h.get("metadata", {})
                title = meta.get("title")
                source_type = meta.get("source_type")
                if source_type == "file" or (source_type == "url" and not (title and title.endswith("_imported"))):
                    if title:
                        matched_names.add(title)
        except Exception as e:
            print(f"[Graph Search] Retriever error: {e}")
            
        # Keyword fallback for title and tags
        for note in active_notes:
            if query_lower in note["name"].lower() or any(query_lower in t.lower() for t in note["tags"]):
                matched_names.add(note["name"])
                
        # Limit nodes to 200: seed nodes first, then 1-hop neighbors
        seed_nodes = [active_notes_map[name] for name in matched_names if name in active_notes_map]
        selected_names = set(n["name"] for n in seed_nodes)
        
        # 1-hop WikiLink neighbors
        wikilink_neighbors = set()
        for seed in seed_nodes:
            for other in active_notes:
                if other["name"] not in selected_names:
                    if other["name"] in seed["wikilinks"] or seed["name"] in other["wikilinks"]:
                        wikilink_neighbors.add(other["name"])
                        
        for name in wikilink_neighbors:
            if len(selected_names) >= 200:
                break
            selected_names.add(name)
            
        # 1-hop Shared Tag neighbors
        if len(selected_names) < 200:
            tag_neighbors = set()
            for seed in seed_nodes:
                for other in active_notes:
                    if other["name"] not in selected_names:
                        if any(t in other["tags"] for t in seed["tags"]):
                            tag_neighbors.add(other["name"])
                            
            for name in tag_neighbors:
                if len(selected_names) >= 200:
                    break
                selected_names.add(name)
    else:
        # Sort by recency and take 100
        sorted_notes = sorted(active_notes, key=lambda x: x["last_modified"], reverse=True)
        selected_notes = sorted_notes[:100]
        selected_names = {n["name"] for n in selected_notes}
        
    # Build final node array
    nodes = []
    for name in selected_names:
        note = active_notes_map[name]
        is_match = name in matched_names if query else False
        nodes.append({
            "id": name,
            "name": name,
            "type": note["type"],
            "tags": note["tags"],
            "is_match": is_match
        })
        
    # Build final edges array
    links = []
    selected_notes_list = [active_notes_map[name] for name in selected_names if name in active_notes_map]
    for i, u in enumerate(selected_notes_list):
        for v in selected_notes_list[i+1:]:
            u_name = u["name"]
            v_name = v["name"]
            
            is_wiki = v_name in u.get("wikilinks", set()) or u_name in v.get("wikilinks", set())
            
            shared_tags = set(u["tags"]).intersection(set(v["tags"]))
            is_tag = len(shared_tags) > 0
            
            if is_wiki:
                links.append({
                    "source": u_name,
                    "target": v_name,
                    "type": "wiki"
                })
            elif is_tag:
                links.append({
                    "source": u_name,
                    "target": v_name,
                    "type": "tag",
                    "tag": list(shared_tags)[0]
                })
                
    return {"nodes": nodes, "links": links}

@app.get("/api/index")
async def index_endpoint():
    return {"categories": get_index_categories()}

@app.get("/stats")
async def stats_endpoint():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, retriever.stats)

# ─── UPLOAD ENDPOINT ──────────────────────────────────────────
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    Upload any file. Routes automatically:
      .md            → data/notes/       (Notes Vault)
      .pdf .docx .txt → data/google_drive/ (Documents)
      anything else  → data/raw/         (Raw Files)
    Then immediately ingests into ChromaDB.
    """
    filename = file.filename
    dest_dir, category = route_upload(filename)
    dest_path = dest_dir / filename

    # Handle name collisions
    if dest_path.exists():
        stem = Path(filename).stem
        ext  = Path(filename).suffix
        ts   = datetime.now().strftime("%H%M%S")
        dest_path = dest_dir / f"{stem}_{ts}{ext}"

    # Save file
    content_bytes = await file.read()
    dest_path.write_bytes(content_bytes)

    # For .md files, auto-add frontmatter if missing
    if dest_path.suffix.lower() == ".md":
        text = dest_path.read_text(encoding="utf-8", errors="replace")
        fixed = auto_add_frontmatter(text, filename)
        dest_path.write_text(fixed, encoding="utf-8")

    # Ingest into ChromaDB in background (non-blocking)
    async def _do_ingest():
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                _executor, lambda: _ingest(file=str(dest_path))
            )
        except Exception as e:
            print(f"[Upload] Ingest warning: {e}")

    background_tasks.add_task(_do_ingest)

    return {
        "status": "ok",
        "filename": dest_path.name,
        "saved_to": str(dest_path.relative_to(_ROOT_DIR)),
        "category": category,
        "size_bytes": len(content_bytes),
    }

# ─── URL / YouTube / Text Ingest ─────────────────────────────
@app.post("/ingest")
async def ingest_endpoint(req: IngestRequest, background_tasks: BackgroundTasks):
    if not any([req.url, req.youtube, req.text]):
        raise HTTPException(400, "Provide url, youtube, or text.")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        lambda: _ingest(url=req.url, youtube=req.youtube, text=req.text, title=req.title or "")
    )
    return result

# ─── Chat (non-blocking) ──────────────────────────────────────
@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    loop = asyncio.get_event_loop()
    hits = await loop.run_in_executor(_executor, lambda: retriever.retrieve(req.question, n=req.n_results))
    if not hits:
        return {"answer": "I couldn't find relevant content in your knowledge base. Try uploading more notes!", "sources": []}
    context = retriever.format_context(hits)
    answer = await loop.run_in_executor(
        _executor, lambda: generator.generate(req.question, context, history=req.history)
    )
    sources_seen, sources = set(), []
    for hit in hits:
        meta = hit["metadata"]
        doc_id = meta.get("doc_id", "")
        if doc_id not in sources_seen:
            sources_seen.add(doc_id)
            sources.append({"title": meta.get("title","Unknown"), "source": meta.get("source",""), "source_type": meta.get("source_type","")})
    return {"answer": answer, "sources": sources}

# ─── Search (non-blocking) ────────────────────────────────────
@app.post("/search")
async def search_endpoint(req: SearchRequest):
    loop = asyncio.get_event_loop()
    hits = await loop.run_in_executor(_executor, lambda: retriever.retrieve(req.query, n=req.n_results))
    return {"results": [{"content": h["content"][:500], "title": h["metadata"].get("title",""),
                         "source": h["metadata"].get("source",""), "source_type": h["metadata"].get("source_type",""),
                         "score": h.get("rrf_score",0)} for h in hits]}

# ─── Nightly Trigger ──────────────────────────────────────────
@app.post("/api/run-nightly")
async def run_nightly(background_tasks: BackgroundTasks):
    import subprocess as sp
    def _run():
        sp.run([sys.executable, str(_ROOT_DIR / "src" / "daily_brief.py")], capture_output=False)
    background_tasks.add_task(_run)
    return {"status": "started", "message": "Nightly sync triggered. Check back in ~2 minutes."}

# ─── Run ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("api:app", host=os.getenv("API_HOST", "127.0.0.1"),
                port=int(os.getenv("API_PORT", 8000)), reload=False, workers=1)
