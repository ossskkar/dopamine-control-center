---
name: mission-eventually
description: Full control over the "Mission Eventually" system — a separate long-term / someday board of big missions, stored under the top-level "mission" key in p100k-data/data.json. Use when the user talks about their missions, someday/eventually goals, or long-term ambitions and wants to add, list, view, edit, re-status (someday/active/done), break into steps, check off steps, or delete them. This is NOT the todo list — do not use it for everyday todo items (that is the separate add-todo skill), and never touch the "todo" data here.
---

# mission-eventually

Full-control manager for **Mission Eventually**: the long-term / "someday" board. It is a distinct system from the todo list.

**Boundary:** this skill only ever reads and writes the top-level `mission` object and its `meta._mi_<id>` timestamps. It must never modify the `todo` object. Conversely, the `add-todo` skill handles everyday todos — if the user is adding a routine task ("remind me to…", "add a todo…"), that is add-todo, not this. When unsure which system the user means, ask.

## Data shape

`p100k-data/data.json` (compact single-line JSON — never reformat) holds:

- `mission`: object keyed by mission id (`m…`). Each mission is
  `{id, title, note, due, status, steps[], ts}`.
  - `status` ∈ `someday` | `active` | `done` (default `someday` — the "eventually" state).
  - `steps`: ordered `{id, text, done}`.
- `meta["_mi_<id>"]`: per-mission last-modified ms timestamp (sync).

## Driving it

Everything goes through the helper (it handles ids, the meta timestamp, validation, and byte-exact formatting). Each call prints one JSON line describing the result — read it, then tell the user in plain language. Run from the skill dir or give an absolute path.

```bash
M=".claude/skills/mission-eventually/mission.py"

# create
python3 $M add --title "Run a sub-4h marathon" --note "after the Oct race" --due 2027-05-01 --status active

# list (optionally filter by status)
python3 $M list
python3 $M list --status active

# view one in full
python3 $M get "marathon"

# edit fields (only the flags you pass change; --due "" clears the date)
python3 $M update "marathon" --note "new plan" --due 2027-06-01

# change status
python3 $M status "marathon" done          # someday | active | done

# steps
python3 $M step "marathon" add "Build a base mileage of 50km/week"
python3 $M step "marathon" done 1           # 1-based index, or a step id
python3 $M step "marathon" undone 1
python3 $M step "marathon" rm 1

# delete a whole mission
python3 $M rm "marathon"
```

`REF` (the `"marathon"` above) matches by exact mission id first, else a
case-insensitive title substring. If a title is ambiguous the tool errors with
the candidates — pass the id it prints.

## Workflow

1. Map what the user said to the right subcommand(s). Parse a `due` date only if clearly stated; convert relative dates ("next spring", "May 2027") to `YYYY-MM-DD`.
2. Run the helper. For several changes in one breath, run it several times.
3. **Sync** to `p100k-data` on branch `claude/load-wcsj46`:

   ```bash
   cd ../p100k-data \
     && git add data.json \
     && git commit -m "mission: <what changed>" \
     && git push -u origin claude/load-wcsj46
   ```

4. Confirm to the user in one line — the mission and what changed. Don't dump JSON unless they ask to see raw data.

## Notes

- `list`/`get` are read-only; no commit needed for those.
- New missions default to `someday` status — that is the "eventually" bucket. Promote to `active` when they start, `done` when finished.
- The app does not yet render the `mission` key; this system is managed here in Claude Code and stored in the data repo. Say so if the user expects to see it in the app.
