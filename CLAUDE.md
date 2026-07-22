# Claude Optimization Rules
- Mode: Direct code execution. No conversational fluff or pleasantries.
- Output: Return only minimal file diffs or the exact code block requested.
- Docs: Do not explain how the code works unless explicitly asked.
- Scope: Read specific files on-demand; do not scan the whole directory structure.
- `app.html`: never read it whole (~60k tokens). Grep for the feature, then Read with offset/limit.
