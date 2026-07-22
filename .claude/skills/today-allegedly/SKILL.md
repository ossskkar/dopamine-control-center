---
name: today-allegedly
description: Full control over TODAY, ALLEGEDLY — the daily planner in the Dopamine Control Center (the "plan" blocks and "plog" ticks in p100k-data/data.json). Use when the user shapes their day or reports on it: "add a gym block at 7am for an hour", "move lunch to 13:00", "make the run every weekday", "delete the reading block", "I did the run", "untick breakfast", "what's left today", "what does tomorrow look like". Blocks are time-boxed and repeat; ticking is per day. For to-dos with due dates use mission-eventually; for logged runs use project-100k.
---

# today-allegedly

The daily planner: the day as one vertical column of time-boxed blocks. A **block** is the repeating template; a **tick** records that it actually happened on one date.

## Data model (do not reshape it)

`p100k-data/data.json` is compact single-line JSON — never reformat it.

- `plan[<id>]` = `{id:"e…", title, start:"HH:MM", dur:<minutes>, note, icon, color, rep, days[], date, ts}`
- `rep` is `once` (uses `date`) | `daily` | `weekdays` (Mon–Fri) | `weekends` | `custom` (uses `days[]`, **0 = Sunday**).
- `plog["YYYY-MM-DD"][<blockId>]` = epoch ms it was ticked.
- Meta: `_pl_<blockId>` for a block, `_pd_<date>` for a day's ticks. The helper stamps these.
- State is computed from the clock, never stored: `soon` / `now` / `miss` / `done`. Missing is never marked by hand.

## Driving it

`REF` = block id or a title substring; an ambiguous substring errors with the candidates.

```bash
T=".claude/skills/today-allegedly/plan.py"

# --- read ---
python3 $T day                      # today's column with state and tick times
python3 $T day tomorrow             # or a date: 2026-07-25, yesterday, -2
python3 $T blocks                   # every block in the plan
python3 $T stats                    # did it / missed / still to go

# --- shape the day ---
python3 $T add --title "Gym" --start 07:00 --dur 60 --rep weekdays --icon 🏃
python3 $T add --title "Dentist" --start 15:30 --dur 45 --on 2026-07-28   # one-off
python3 $T add --title "Dutch" --start 20:00 --dur 30 --days mon,wed,fri  # custom days
python3 $T edit "Gym" --start 07:30 --dur 45
python3 $T edit "Gym" --rep daily --note "easy pace"
python3 $T rm "Dentist"             # also clears its ticks

# --- what actually happened ---
python3 $T tick "Gym"               # done now
python3 $T tick "Gym" --at 07:35    # done at a stated time
python3 $T tick "Gym" --date yesterday
python3 $T untick "Gym"
```

## Workflow

1. Run the helper (once per change). Convert times and relative dates yourself: "7pm" → `19:00`, "Friday" → the `YYYY-MM-DD`.
2. **Sync** — the app only sees it after a push to `main`:

   ```bash
   cd ../p100k-data && git pull --rebase --quiet \
     && git add data.json \
     && git commit -m "plan: <what changed>" \
     && git push
   ```

   Pull **before** editing too if the app may have written since.
3. Confirm in a few words — `Done — Gym now 07:30, weekdays`. No JSON dumps.

## Notes

- `dur` is clamped to 5–720 minutes; blocks that would cross midnight just run past the bottom of the day — the app does not split them.
- `edit` only changes the flags you pass; everything else stays.
- Deleting a block removes its ticks on every date. Confirm before deleting one the user has been running for a while.
- There is no "skipped" state: a block you deliberately didn't do reads the same as one you forgot.
- This skill touches `plan`, `plog` and their `meta` keys only.
