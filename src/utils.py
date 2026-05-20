"""
utils.py — Shared Utility Functions
"""

import os
import re
import sys
from typing import List
from datetime import datetime

# Ensure stdout/stderr use UTF-8 on Windows to avoid charmap errors with emoji
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    """
    Split text into overlapping chunks by token approximation.
    Uses sentence boundaries for cleaner splits.
    ~4 chars ≈ 1 token.
    """
    if not text or not text.strip():
        return []

    char_size = chunk_size * 4
    char_overlap = overlap * 4

    # Try to split on sentence/paragraph boundaries
    sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= char_size:
            current += (" " if current else "") + sentence
        else:
            if current:
                chunks.append(current.strip())
            # Start new chunk with overlap
            if len(current) > char_overlap:
                overlap_text = current[-char_overlap:]
                current = overlap_text + " " + sentence
            else:
                current = sentence

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if len(c) > 50]  # Filter tiny chunks


def log(message: str, level: str = "INFO"):
    """Simple logger with timestamp. Safe on Windows cp1252 consoles."""
    ts = datetime.utcnow().strftime("%H:%M:%S")
    prefix = {"INFO": "[INFO]", "WARN": "[WARN]", "ERROR": "[ERR ]"}  .get(level, "")
    line = f"[{ts}] {prefix} {message}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode('ascii', errors='replace').decode('ascii'))


def get_db(path: str = "./data/metadata.db"):
    """Get SQLite connection for document metadata."""
    import sqlite3
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            source_type TEXT,
            chunks INTEGER,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    return re.sub(r"[^\w\-_\. ]", "_", name)[:100]
