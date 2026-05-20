# 🧠 Second Brain Agent Rules & Style Guide
This document defines the structural and formatting constraints that all background processes, subagents, and editors must respect when working with the Second Brain knowledge repositories.

---

## 📌 Core Ingestion & Modification Principles

### 1. Journal and Raw Entries Integrity
- **CRITICAL:** Never overwrite, modify, or delete raw personal journal entries (files under `journal/` or starting with `journal-`).
- **Allowed:** You may only append analytical summaries, action items, or connection notes at the very bottom of the file under a clear horizontal rule (`---`) and a heading: `## 🤖 AI Summary & Insights`.
- Preserve all original markdown content, personal formatting, typos, and raw notes exactly as written.

### 2. Centralized Index Maintenance
- Maintain a centralized `index.md` at the root of the notes directory.
- This index acts as the entry point to the entire knowledge base.
- When new topics or documents are added, reference them in `index.md` under their appropriate categories.

### 3. Cross-Referencing Format
- Always use standard **WikiLinks** (`[[Note Name]]` or `[[Note Name#Section]]`) format for referencing other notes.
- Do not use absolute file paths or relative pathing (like `../notes/file.md`) inside the markdown body unless specifically requested.
- Ensure the casing of the linked filename matches the target file exactly to prevent broken links on case-sensitive platforms.

---

## 🗂️ Note Taxonomy & Layout

All automatically generated summaries, daily briefs, or refined notes must follow this frontmatter structure:

```markdown
---
type: [brief | concept | research | task | journal]
created: YYYY-MM-DD HH:MM:SS
tags: [tag1, tag2]
sources: [source_url_or_filepath]
status: [raw | processed | archived]
---
```

### Formatting Requirements
- **Headers:** Use ATX-style headers (`#`, `##`, `###`).
- **Lists:** Prefer dash `-` for unordered lists.
- **Checklists:** Use `- [ ]` for incomplete actions, and `- [x]` for completed tasks.

---

## 🤖 Background Agent Guidelines

- **Subagent A (Task Master):** Limit tasks extracted to actionable, high-priority items. Do not clutter lists with trivial tasks.
- **Subagent B (Archivist):** Run semantic correlation analyses. Create links between concepts only if similarity is high (cosine score > 0.75). Explain the link in a parenthetical note.
- **Subagent C (Researcher):** Verify facts using reliable sources. Provide concise summary blocks of external references with full URL citations.
