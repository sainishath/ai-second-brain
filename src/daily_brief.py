"""
daily_brief.py — Nightly Ingestion and Analysis Orchestration
Performs:
  1. Local notes scanning & vector indexing via NotesProcessor.
  2. Google Drive folder scanning & ingestion (simulating Workspace integration).
  3. Parallel subagent analysis (Task Master, Archivist, Researcher).
  4. Generates a consolidated "Daily Brief.md" in the vault.
Usage:
  python src/daily_brief.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add src to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notes_processor import NotesProcessor
from subagents import TaskMasterSubagent, ArchivistSubagent, ResearcherSubagent
from ingest import ingest as _ingest
from utils import log

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", ".env"))

_ROOT_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent

def run_daily_orchestration():
    log("=========================================")
    log("🚀 STARTING NIGHTLY SECOND BRAIN RUN")
    log("=========================================")

    # Directories setup
    notes_dir = _ROOT_DIR / "data" / "notes"
    drive_dir = _ROOT_DIR / "data" / "google_drive"
    briefs_dir = _ROOT_DIR / "data" / "briefs"
    
    notes_dir.mkdir(parents=True, exist_ok=True)
    drive_dir.mkdir(parents=True, exist_ok=True)
    briefs_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")

    # ─── 1. Scan Google Drive Folder (Workspace Sync) ─────────────────
    log(f"[Sync] Scanning Google Drive sync folder: {drive_dir}")
    drive_files_ingested = []
    
    # Ingest any new/untracked files in data/google_drive
    for ext in ["*.pdf", "*.txt", "*.md", "*.docx"]:
        for path in drive_dir.rglob(ext):
            try:
                # We can check if it is already in our DB by looking at the document database metadata
                # Let's ingest it directly. Ingest function handles hashing/upserting in Chroma DB.
                log(f"[Sync] Ingesting Google Drive file: {path.name}")
                res = _ingest(file=str(path))
                if res.get("status") == "ok":
                    drive_files_ingested.append({
                        "name": path.name,
                        "title": res.get("title", path.stem),
                        "chunks": res.get("chunks", 0)
                    })
            except Exception as e:
                log(f"[Sync] Failed to ingest {path.name}: {e}", "ERROR")

    # ─── 2. Run Notes Processor (Local Vault) ────────────────────────
    log("[Processor] Running Notes Processor pipeline...")
    processor = NotesProcessor(notes_dir=str(notes_dir))
    processed_notes = processor.run()
    
    newly_processed = [n for n in processed_notes if n.get("status") == "processed"]
    log(f"[Processor] Indexed {len(newly_processed)} new/modified notes.")

    # ─── 3. Run Subagent A: Task Master ──────────────────────────────
    task_master = TaskMasterSubagent()
    extracted_tasks = task_master.run(notes_dir)

    # ─── 4. Run Subagent B: Archivist ────────────────────────────────
    archivist = ArchivistSubagent()
    wiki_connections = archivist.run(notes_dir)

    # ─── 5. Run Subagent C: Researcher ───────────────────────────────
    researcher = ResearcherSubagent()
    research_runs = researcher.run(notes_dir)

    # ─── 6. Compile Daily Brief.md ───────────────────────────────────
    log("[Brief] Generating Daily Brief...")
    
    brief_content = f"""---
type: brief
created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
status: processed
tags: [daily-brief, summary]
---

# 📅 Daily Brief: {today_str}
*Generated automatically by your Second Brain Nightly Administrator at {datetime.now().strftime("%H:%M:%S")}*

---

## 📥 Ingestion & Sync Summary
Here are the files added and synchronized to your Second Brain today:

### 🖥️ Local Notes Ingested
"""
    if newly_processed:
        for note in newly_processed:
            brief_content += f"- **[[{note['title']}]]** - Categorized: *{', '.join(note.get('themes', ['General']))}*\n"
    else:
        brief_content += "*No new local notes indexed today.*\n"

    brief_content += "\n### ☁️ Google Workspace Docs Synced\n"
    if drive_files_ingested:
        for doc in drive_files_ingested:
            brief_content += f"- **{doc['title']}** ({doc['name']}) - Indexed into {doc['chunks']} semantic chunks\n"
    else:
        brief_content += "*No new Google Drive documents imported today.*\n"

    brief_content += "\n---\n\n## ⚡ Action Items Checklist (Subagent A - Task Master)\n"
    total_tasks = sum(len(n["tasks"]) for n in extracted_tasks)
    if total_tasks > 0:
        brief_content += f"Extracted **{total_tasks}** action items from your daily scratchpads:\n\n"
        for item in extracted_tasks:
            brief_content += f"### From note: [[{Path(item['file']).stem}]]\n"
            for task in item["tasks"]:
                brief_content += f"{task}\n"
            brief_content += "\n"
    else:
        brief_content += "*No action items found in your recent notes today.*\n"

    brief_content += "\n---\n\n## 🔗 Concept Connections Added (Subagent B - Archivist)\n"
    if wiki_connections:
        brief_content += f"Connected **{len(wiki_connections)}** notes based on semantic similarity overlaps:\n\n"
        for conn in wiki_connections:
            brief_content += f"- Linked **[[{Path(conn['file']).stem}]]** with: {', '.join([f'[[{l}]]' for l in conn['links']])}\n"
    else:
        brief_content += "*No new conceptual overlaps or links identified today.*\n"

    brief_content += "\n---\n\n## 🔍 Fact-Checking & Deep Research (Subagent C - Researcher)\n"
    if research_runs:
        brief_content += f"Verified and pulled background documentation summaries for **{len(research_runs)}** terms:\n\n"
        for run in research_runs:
            brief_content += f"### From note: [[{Path(run['file']).stem}]]\n"
            for res in run["results"]:
                brief_content += f"- **{res['query']}**: {res['summary']}\n"
            brief_content += "\n"
    else:
        brief_content += "*No new research tags or placeholders detected to resolve.*\n"

    brief_content += """
---
*Note: This brief was generated based on the agent rule file `.agents/rules/brain-style.md`. All raw journal logs remain untouched.*
"""

    # Save brief in two locations: briefs dir (for archive) and notes dir (for Obsidian/local viewing)
    brief_filename = f"Daily Brief {today_str}.md"
    
    # 1. Archive folder
    brief_archive_path = briefs_dir / brief_filename
    brief_archive_path.write_text(brief_content, encoding="utf-8")
    
    # 2. Vault folder (centralized access point)
    brief_vault_path = notes_dir / "Daily Brief.md"
    brief_vault_path.write_text(brief_content, encoding="utf-8")

    # 3. Add Daily Brief link to the index
    processor.update_centralized_index(brief_vault_path, ["General"])

    log(f"[Brief] Daily Brief saved at: {brief_archive_path}")
    log(f"[Brief] Centralized Daily Brief updated at: {brief_vault_path}")
    log("=========================================")
    log("✅ NIGHTLY PROCESS COMPLETED SUCCESSFULLY")
    log("=========================================")
    
    return {
        "status": "success",
        "newly_processed": len(newly_processed),
        "workspace_synced": len(drive_files_ingested),
        "tasks_extracted": total_tasks,
        "connections_made": len(wiki_connections),
        "research_completed": len(research_runs)
    }

if __name__ == "__main__":
    run_daily_orchestration()
