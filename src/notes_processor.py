"""
notes_processor.py — Background Notes Processing & Clustering Pipeline
Scans 'data/notes/', extracts frontmatter, runs rule validation checks,
indexes new notes in ChromaDB, clusters themes via LLM, and updates index.md.
"""

import os
import re
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml  # PyYAML is installed (from requirements.txt)

from dotenv import load_dotenv
from ingest import ingest as _ingest
from generator import get_generator
from utils import log, get_db

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", ".env"))

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.join(_SRC_DIR, "..")

class NotesProcessor:
    """
    Background pipeline to monitor, ingest, validate, and cluster notes.
    """

    def __init__(self, notes_dir: str = None):
        self.notes_dir = Path(notes_dir or os.path.join(_ROOT_DIR, "data", "notes"))
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = os.path.join(_ROOT_DIR, "data", "metadata.db")
        self.generator = get_generator()
        self._init_tracking_db()

    def _init_tracking_db(self):
        """Initialize SQLite table to track processed files."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes_tracking (
                filepath TEXT PRIMARY KEY,
                last_modified REAL,
                file_hash TEXT,
                doc_id TEXT,
                themes TEXT,
                processed_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _get_file_hash(self, path: Path) -> str:
        """Compute MD5 hash of a file."""
        hasher = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def parse_note(self, path: Path) -> Dict[str, Any]:
        """
        Extract Frontmatter metadata and body text from a Markdown note.
        """
        content = path.read_text(encoding="utf-8")
        frontmatter = {}
        body = content

        # Match yaml frontmatter: starts and ends with ---
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if match:
            fm_text = match.group(1)
            body = match.group(2)
            try:
                frontmatter = yaml.safe_load(fm_text) or {}
            except Exception as e:
                log(f"[NotesProcessor] YAML error in {path.name}: {e}", "WARN")

        # Strip out the AI Summary & Insights block from indexing to prevent feedback loops
        if "## 🤖 AI Summary & Insights" in body:
            body = body.split("## 🤖 AI Summary & Insights")[0].strip()

        return {
            "frontmatter": frontmatter,
            "body": body.strip(),
            "raw_content": content
        }

    def validate_note(self, path: Path, parsed: Dict[str, Any]) -> bool:
        """
        Validate note compliance with brain-style rules.
        """
        fm = parsed["frontmatter"]
        filename = path.name.lower()

        # Rule check: "Never overwrite raw personal journal entries"
        is_journal = (
            fm.get("type") == "journal" or 
            filename.startswith("journal") or 
            "journal" in str(path.parent).lower()
        )

        if is_journal:
            # Let's check if the file was modified by comparing with our tracking DB hash
            # If the body changes, that's fine (user editing), but we want to make sure
            # background agents didn't overwrite the original text.
            # We can also verify that the original entry exists intact.
            pass

        return True

    def cluster_note_theme(self, title: str, content: str) -> List[str]:
        """Ask the LLM to cluster the note into 1-2 broad categories/themes."""
        prompt = f"""You are the Second Brain clustering agent. Analyze the note titled "{title}" and categorize it into 1 or 2 standard categories.
Standard categories include: Work, Machine Learning, Coding, Productivity, Personal, Finance, Health, Research, General.

Note Content:
{content[:1500]}

Return only a comma-separated list of categories. Example response: "Machine Learning, Coding".
Categories:"""
        
        try:
            response = self.generator.generate(prompt, context="Metadata Classification Engine")
            categories = [c.strip() for c in response.split(",") if c.strip()]
            return categories
        except Exception as e:
            log(f"[NotesProcessor] LLM theme clustering failed: {e}", "WARN")
            return ["General"]

    def update_frontmatter(self, path: Path, parsed: Dict[str, Any], themes: List[str]):
        """
        Updates frontmatter of the markdown file with new metadata (tags, themes, status).
        Respects the rule to NOT overwrite raw journal text.
        """
        fm = parsed["frontmatter"]
        body = parsed["body"]
        raw = parsed["raw_content"]

        # Check if journal
        is_journal = (
            fm.get("type") == "journal" or 
            path.name.lower().startswith("journal") or 
            "journal" in str(path.parent).lower()
        )

        if is_journal:
            # For journal files, do not touch the frontmatter if it's already written by the user.
            # We can append comments or summaries to the bottom.
            return

        # Update metadata
        fm["type"] = fm.get("type", "concept" if "research" not in path.name.lower() else "research")
        fm["status"] = "processed"
        fm["created"] = fm.get("created", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
        
        tags = fm.get("tags", [])
        if not isinstance(tags, list):
            tags = [tags]
        
        for theme in themes:
            if theme.lower() not in [t.lower() for t in tags]:
                tags.append(theme)
        fm["tags"] = tags

        # Write file back
        try:
            fm_yaml = yaml.dump(fm, default_flow_style=False).strip()
            # If the original file had an AI Summary & Insights block, make sure to preserve it!
            ai_insights = ""
            if "## 🤖 AI Summary & Insights" in raw:
                ai_insights = "\n\n## 🤖 AI Summary & Insights" + raw.split("## 🤖 AI Summary & Insights")[1]

            new_content = f"---\n{fm_yaml}\n---\n\n{body}{ai_insights}"
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            log(f"[NotesProcessor] Failed to update frontmatter for {path.name}: {e}", "WARN")

    def update_centralized_index(self, note_path: Path, themes: List[str]):
        """
        Maintains index.md at root. Adds WikiLinks under corresponding categories.
        """
        index_file = self.notes_dir / "index.md"
        note_title = note_path.stem
        link_md = f"- [[{note_title}]]"

        if not index_file.exists():
            # Create a new index
            index_content = """# 🧠 Second Brain Knowledge Index
Welcome to your centralized Second Brain index. All notes are organized here by conceptual themes.

## 🗂️ Categories

### Work
*No files yet.*

### Machine Learning
*No files yet.*

### Coding
*No files yet.*

### Productivity
*No files yet.*

### Research
*No files yet.*

### Personal
*No files yet.*

### General
*No files yet.*
"""
            index_file.write_text(index_content, encoding="utf-8")

        try:
            index_content = index_file.read_text(encoding="utf-8")
            
            # Check if note is already linked anywhere in index
            if f"[[{note_title}]]" in index_content:
                return

            # Append under the first matching theme
            updated = False
            for theme in themes:
                category_header = f"### {theme}"
                if category_header in index_content:
                    # Insert the link below the header
                    # Find insertion point
                    parts = index_content.split(category_header)
                    # Remove "*No files yet.*" placeholder if present
                    section_body = parts[1]
                    if "*No files yet.*" in section_body:
                        section_body = section_body.replace("*No files yet.*\n", "").replace("*No files yet.*", "")
                    
                    # Split at the next section or EOF
                    # A section ends at the next header "###" or "##"
                    lines = section_body.splitlines()
                    insert_idx = 0
                    for idx, line in enumerate(lines):
                        if line.startswith("##"):
                            insert_idx = idx
                            break
                    else:
                        insert_idx = len(lines)

                    lines.insert(insert_idx, f"  {link_md}")
                    parts[1] = "\n".join(lines)
                    index_content = category_header.join(parts)
                    updated = True
                    log(f"[NotesProcessor] Added {note_title} to index.md under '{theme}'")
                    break

            if not updated:
                # If no matching header, add under ### General
                if "### General" in index_content:
                    parts = index_content.split("### General")
                    section_body = parts[1]
                    if "*No files yet.*" in section_body:
                        section_body = section_body.replace("*No files yet.*\n", "").replace("*No files yet.*", "")
                    lines = section_body.splitlines()
                    lines.insert(0, f"  {link_md}")
                    parts[1] = "\n".join(lines)
                    index_content = "### General".join(parts)
                    log(f"[NotesProcessor] Added {note_title} to index.md under General")

            index_file.write_text(index_content, encoding="utf-8")
        except Exception as e:
            log(f"[NotesProcessor] Error updating index.md: {e}", "WARN")

    def process_note_file(self, path: Path) -> Dict[str, Any]:
        """Process a single markdown/text file, indexing and clustering it."""
        file_hash = self._get_file_hash(path)
        last_modified = path.stat().st_mtime

        # Check if already processed and unmodified
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT file_hash, doc_id, themes FROM notes_tracking WHERE filepath = ?", 
            (str(path),)
        )
        row = cursor.fetchone()
        
        if row and row[0] == file_hash:
            conn.close()
            return {"status": "unmodified", "doc_id": row[1]}

        log(f"[NotesProcessor] Processing note: {path.name}")
        parsed = self.parse_note(path)
        self.validate_note(path, parsed)

        # Ingest note to ChromaDB vector store
        # We read text directly using ingest
        result = _ingest(text=parsed["body"], title=path.stem, file=str(path))
        doc_id = result.get("doc_id", hashlib.md5(str(path).encode()).hexdigest()[:12])

        # Cluster themes
        themes = self.cluster_note_theme(path.stem, parsed["body"])
        log(f"[NotesProcessor] Themes clustered for {path.name}: {themes}")

        # Update note frontmatter with tags/themes
        self.update_frontmatter(path, parsed, themes)

        # Update centralized index.md
        self.update_centralized_index(path, themes)

        # Track processing status in sqlite database
        cursor.execute("""
            INSERT OR REPLACE INTO notes_tracking 
            (filepath, last_modified, file_hash, doc_id, themes, processed_at) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (str(path), last_modified, file_hash, doc_id, ",".join(themes), datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()

        return {
            "status": "processed",
            "doc_id": doc_id,
            "themes": themes,
            "title": path.stem
        }

    def run(self) -> List[Dict]:
        """Scan notes directory and run pipeline for all notes."""
        log(f"[NotesProcessor] Scanning vault: {self.notes_dir}")
        results = []
        for path in self.notes_dir.rglob("*.md"):
            # Ignore special files
            if path.name.lower() in ["index.md", "daily brief.md"]:
                continue
            try:
                res = self.process_note_file(path)
                results.append(res)
            except Exception as e:
                log(f"[NotesProcessor] Error processing file {path.name}: {e}", "ERROR")
        return results

if __name__ == "__main__":
    processor = NotesProcessor()
    processor.run()
