---
name: mission-eventually
description: Full control over the "Mission: Eventually" board — the app's name for the to-do board itself (the top-level "todo" object in p100k-data/data.json), with its projects, tasks, due dates and steps. Use when the user wants to manage the board broadly: list/add/rename/reorder/delete projects, edit/complete/move/delete tasks, or add and check off a task's steps. Distinct skill from add-todo, which only quick-captures one new task; both act on the same real board because it is the one board the app renders.
---

# mission-eventually

Full-control manager for **Mission: Eventually** — the app's display name for the to-do board (`todo` data). This skill can do anything to the board's structure and contents; `add-todo` is the lightweight "just add one task" capture. They are separate skills that share the same real data, because Mission: Eventually *is* that board.

**When to use which:** a plain "add a todo / remind me to X" → `add-todo`. Anything else about the board — listing, editing, completing, moving, reordering, deleting, steps, projects → this skill. When unsure, this skill's `tasks`/`projects` read commands are safe to explore with.

## Data model (do not reshape it)

`p100k-data/data.json` is compact single-line JSON — never reformat. Under `todo`:

- **Project** `{id:"p…", name, note, ts, tasks[]}`, keyed by id. Display order = key order.
- **Task** `{id:"t…", title, note, due, done, steps[]}`.
- **Step** `{id:"s…", title, done}` (same label key as tasks/resources).
- `meta["_td_<projectId>"]` = per-project sync timestamp.

## Driving it

All ops go through the helper (ids, `_td_` timestamps, validation, byte-exact formatting handled for you). Each prints one JSON line — read it, then reply in plain language. `PREF`/`TREF` match by id or by a name/title substring; ambiguous matches error with candidates.

```bash
M=".claude/skills/mission-eventually/mission.py"

# --- projects ---
python3 $M projects                              # list with task counts
python3 $M project-add  --name "Travel" --note "trips to plan"
python3 $M project-edit "Travel" --name "Trips"
python3 $M project-move "Trips" --to 1           # reorder to position 1
python3 $M project-rm   "Trips"                  # deletes its tasks too

# --- tasks (TREF = task id or title substring, any project) ---
python3 $M tasks                                 # all tasks; or: tasks "Health"
python3 $M task-add  "Health" --title "Book dentist" --due 2026-08-01
python3 $M task-edit "dentist" --note "molar" --due 2026-08-05
python3 $M task-done "dentist"                   # / task-undone
python3 $M task-move "dentist" --to "Admin"      # move between projects
python3 $M task-rm   "dentist"

# --- steps within a task ---
python3 $M step-add    "budget" --text "Export last 3 months"
python3 $M step-done   "budget" 1                # 1-based index or step id
python3 $M step-undone "budget" 1
python3 $M step-rm     "budget" 1
```

## Workflow

1. Map the request to subcommand(s). Parse a `due` date only when clearly stated; convert relative dates to `YYYY-MM-DD`.
2. Run the helper (several times for several changes). Read-only `projects`/`tasks` need no commit.
3. **Sync** to `p100k-data` on `claude/load-wcsj46` (per the branch rules), then it is pushed onward as configured:

   ```bash
   cd ../p100k-data \
     && git add data.json \
     && git commit -m "mission: <what changed>" \
     && git push -u origin claude/load-wcsj46
   ```

4. Confirm in one line. Don't dump JSON unless asked.

## Notes

- Destructive ops (`project-rm`, `task-rm`) can't be undone from here — confirm with the user before deleting a project (it takes its tasks with it).
- Step label is stored under `title` (matching tasks/resources). If the app still renders steps blank, share `app.html` and I'll align the exact field names.
- This skill only reads/writes `todo` and its `meta._td_` timestamps — never other data areas.
