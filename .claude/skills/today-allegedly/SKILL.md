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

python3 $T copy "Gym" --start 18:00 # same block again, later in the day
python3 $T seed                     # "an ordinary day": 8 starter blocks (empty plan only)
python3 $T clear --date yesterday   # wipe that day's ticks (--blocks also deletes its blocks)

# --- what actually happened ---
python3 $T tick "Gym"               # done now
python3 $T tick "Gym" --at 07:35    # done at a stated time
python3 $T tick "Gym" --date yesterday
python3 $T untick "Gym"
```

## Saying it in plain language

| What the user says | What to run |
|---|---|
| "gym at 7 every weekday, an hour" | `add --title Gym --start 7am --dur 60 --rep weekdays` |
| "dutch class 8pm Mondays and Wednesdays" | `add --title "Dutch class" --start 8pm --dur 60 --days mon,wed` |
| "dentist Friday at half three" | `add --title Dentist --start 15:30 --dur 45 --on <that Friday>` |
| "push the gym back half an hour" | `edit Gym --start 07:30` |
| "put another gym in at six" | `copy Gym --start 18:00` |
| "I did it at twenty past" | `tick Gym --at 07:20` |
| "no I didn't, undo that" | `untick Gym` |
| "give me a normal day to start from" | `seed` |
| "clear today, it's a write-off" | `clear` |
| "what's left?" / "how did today go?" | `stats` / `day` |

Times accept `7am`, `19:00`, `0730`. Dates accept `today`, `yesterday`, `-2`, `2026-07-25` — work out "Friday" or "next week" yourself and pass the date.

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
- Two blocks can share a title. `tick` resolves that by clock (the one whose window covers `--at`, else the last one already started); `edit`, `rm`, `copy` and `untick` refuse to guess and list the candidates with their times and ids — re-run naming one.
- `seed` refuses to run on a plan that already has blocks unless you pass `--force`.
- Deleting a block removes its ticks on every date. Confirm before deleting one the user has been running for a while.
- There is no "skipped" state: a block you deliberately didn't do reads the same as one you forgot.
- This skill touches `plan`, `plog` and their `meta` keys only.
