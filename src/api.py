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

# Ensure dirs exist
for d in [_NOTES_DIR, _DRIVE_DIR, _BRIEFS_DIR, _RAW_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── App ──────────────────────────────────────────────────────
app = FastAPI(title="AI Second Brain", version="2.1.0")
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
                    for l in content[3:end].splitlines():
                        if ":" in l:
                            k, _, v = l.partition(":")
                            fm[k.strip()] = v.strip()
            tags_raw = fm.get("tags", "[]")
            tags = re.findall(r"\w[\w-]*", tags_raw)
            word_count = len(re.sub(r"[^a-zA-Z ]", " ", content).split())
            links = list(set(re.findall(r"\[\[([^\]]+)\]\]", content)))
            has_ai = "## 🤖 AI Summary" in content
            notes.append({
                "name": path.stem, "filename": path.name,
                "type": fm.get("type", "note"), "created": fm.get("created", ""),
                "tags": tags, "word_count": word_count, "links": links,
                "has_ai_insights": has_ai, "status": fm.get("status", ""),
                "preview": re.sub(r"\s+", " ", re.sub(r"---.*?---", "", content, flags=re.DOTALL).strip()[:200])
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
    dashboard_path = _ROOT_DIR / "src" / "dashboard.html"
    if dashboard_path.exists():
        return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))
    return {"name": "AI Second Brain", "status": "running"}

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

@app.get("/api/note/{name}")
async def note_detail(name: str):
    path = _NOTES_DIR / f"{name}.md"
    if not path.exists():
        raise HTTPException(404, "Note not found")
    return {"name": name, "content": path.read_text(encoding="utf-8")}

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
    uvicorn.run("api:app", host=os.getenv("API_HOST","0.0.0.0"),
                port=int(os.getenv("API_PORT", 8000)), reload=False, workers=1)
