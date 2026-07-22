---
name: board-query
description: Read-only queries about the Project 100K data — the "Mission: Eventually" board (projects, tasks, steps) and anything else in p100k-data/data.json. Use when the user asks a question rather than requests a change: "what's on my board", "what's due today / overdue", "find the tax task", "how many steps left on Learn Hermes", "give me a summary", "what's my race date". Never writes and never commits. For making changes use mission-eventually (board) or add-todo (quick capture).
---

# board-query

Answer questions about the board and the rest of the data. **Read-only** — this skill never mutates data and never commits. If the user wants a *change*, use `mission-eventually` (full board control) or `add-todo` (quick capture) instead.

## Driving it

Pick the subcommand that fits the question, run it, then answer the user in plain language from the JSON it prints (don't dump raw JSON unless they ask).

```bash
Q=".claude/skills/board-query/query.py"

python3 $Q dump                    # whole board; --status open|done|all
python3 $Q summary                 # counts + completion per project and totals
python3 $Q find "hermes"           # search projects/tasks/steps for text
python3 $Q today                   # undone tasks due today
python3 $Q overdue                 # undone tasks past their due date
python3 $Q due --on 2026-08-01     # tasks due exactly that day
python3 $Q due --before 2026-08-31 # tasks due on/before that day
python3 $Q raw settings.raceDate   # inspect any key path in data.json
python3 $Q raw                     # list top-level data keys
```

## Notes

- `find` matches task titles/notes, step titles, and project names/notes (case-insensitive).
- `today`/`overdue` use the machine's current date.
- `raw` walks a dot path (`days.2026-07-21`, `todo`, `settings`) so you can answer questions about non-board data (runs, race date, exam progress, flashcards) too — still read-only.
- Because it only reads, no branch/commit/sync step is needed. If a question implies a change, hand off to the write skills.
