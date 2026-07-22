---
name: add-todo
description: Capture a spoken/typed todo into the Project 100K todo system (p100k-data/data.json) and sync it. Use whenever the user, in ordinary conversation, wants something added to their list, mission, or todos — e.g. "add a todo to…", "remind me to…", "put X on my list", "capture: …", "I need to … (add that)". Auto-routes to the best-matching life project (Finance, Health, Home, Admin & paperwork, Learning), falling back to an Inbox, then commits and pushes to p100k-data.
---

# add-todo

Turn something the user says into a task in the Project 100K todo store and sync it immediately.

## What the data looks like

`p100k-data/data.json` (compact, single-line JSON — never reformat it) holds:

- `todo`: object keyed by project id (`p…`). Each project is `{id, name, note, ts, tasks[]}`.
- Each task: `{id, title, note, due, done, steps[]}`.
- `meta["_td_<projectId>"]`: per-project last-modified ms timestamp used for sync.

Existing life projects are typically **Finance, Health, Home, Admin & paperwork, Learning**. Do not hardcode this list — read the file to get the current names.

## Steps

1. **Parse** the user's words into:
   - `title` — the action, short and imperative ("Call the dentist").
   - `note` — any extra detail they gave (optional).
   - `due` — a date only if they clearly stated one; convert relative dates ("tomorrow", "Friday") to `YYYY-MM-DD` using today's date. Otherwise leave empty.

2. **Choose the project.** Read the current project names from `p100k-data/data.json`, then pick the single best semantic match for this task (e.g. a doctor's appointment → Health, a tax form → Admin & paperwork, a course → Learning). If nothing fits well, pass no project — the script drops it in **Inbox** (created on first use). When genuinely torn between two projects, ask the user with `AskUserQuestion` rather than guessing.

3. **Write** the task by running the helper (it handles id generation, the meta timestamp, and byte-exact formatting):

   ```bash
   python3 .claude/skills/add-todo/add_todo.py \
     --title "Call the dentist" \
     --note "" \
     --due "" \
     --project "Health"
   ```

   Omit `--project` to force Inbox. The script prints one JSON line with the project and task it wrote.

4. **Sync** to `p100k-data` on branch `claude/load-wcsj46`:

   ```bash
   cd ../p100k-data \
     && git add data.json \
     && git commit -m "todo: add \"<title>\" to <project>" \
     && git push -u origin claude/load-wcsj46
   ```

   Adjust the `p100k-data` path if it lives elsewhere (`$P100K_DATA` overrides the data path for the script).

5. **Confirm** to the user in one line: the task title, the project it landed in, and the due date if any. Don't dump the JSON.

## Notes

- Multiple todos in one breath → run the script once per task, then a single commit + push.
- The script only appends; it never edits or completes tasks. Removing/checking off is out of scope.
- Keep it quiet: no explanation of the data model unless asked.
