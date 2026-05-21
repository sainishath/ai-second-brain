import sqlite3
import os
from pathlib import Path

db_path = Path("data/metadata.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes_tracking WHERE filepath LIKE '%temp_test_note%' OR filepath LIKE '%example_domain_imported%'")
    cursor.execute("DELETE FROM documents WHERE title LIKE '%temp_test_note%' OR title LIKE '%example_domain_imported%'")
    conn.commit()
    conn.close()
    print("Database records cleaned.")

for f in ["data/notes/temp_test_note.md", "data/notes/example_domain_imported.md"]:
    p = Path(f)
    if p.exists():
        p.unlink()
        print(f"Removed file: {f}")
