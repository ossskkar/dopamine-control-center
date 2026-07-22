---
name: project-100k
description: Full control over PROJECT 100K — the running log in the Dopamine Control Center (the "days" object in p100k-data/data.json) plus the race date. Use when the user logs or changes a run ("ran 8k this morning", "add 5km yesterday at 5:20 pace", "that one was with the pram", "delete Tuesday's run"), or asks about training ("how many km this week", "am I on plan", "how long to the race", "what's my streak"). Writes days and settings.raceDate only; for the to-do board use mission-eventually, for the daily planner use today-allegedly.
---

# project-100k

PROJECT 100K is the running system: a 14-week plan ending at a 100K race. This skill reads and writes the run log and the race date.

## Data model (do not reshape it)

`p100k-data/data.json` is compact single-line JSON — never reformat it.

- `days["YYYY-MM-DD"]` = a plain km number (legacy) **or** `{km, sp, baby}`. `sp` = pace in **seconds per km** (5:20 → 320). `baby: 1` = ran pushing the pram.
- `settings.raceDate` = `YYYY-MM-DD`. The 14-week plan is derived from it: week 1 Monday = Monday of race week minus 13 weeks.
- `meta["<date>"]` = that day's sync timestamp; `meta["_race"]` = the race date's. The helper stamps these on every write.

## Driving it

```bash
P=".claude/skills/project-100k/p100k.py"

# --- log a run (--date takes today | yesterday | -2 | YYYY-MM-DD) ---
python3 $P log --km 8                              # today, 8 km
python3 $P log --date yesterday --km 12 --pace 5:20
python3 $P log --km 5 --baby                       # with the pram
python3 $P log --date 2026-07-20 --km 3 --add      # add 3 km to that day
python3 $P log --date today --no-baby --no-pace    # unset flags
python3 $P rm --date 2026-07-19                    # delete the day

# --- read ---
python3 $P summary                # banked vs plan, streak, race countdown
python3 $P week                   # this plan week: planned vs actual
python3 $P week 9                 # a specific plan week (1–14)
python3 $P days --last 10         # recent days; or --from/--to
python3 $P race                   # race date + plan start
python3 $P race --set 2026-10-17  # move the race
```

## Saying it in plain language

| What the user says | What to run |
|---|---|
| "ran 8k this morning" | `log --km 8` |
| "yesterday was 12 at five twenty" | `log --date yesterday --km 12 --pace 5:20` |
| "that one was with the pram" | `log --date yesterday --baby` |
| "add another 3k to Monday" | `log --date <that Monday> --km 3 --add` |
| "scrap Sunday's run" | `rm --date <that Sunday>` |
| "how am I doing?" / "am I on plan?" | `summary` / `week` |
| "push the race back a week" | `race --set <new date>` |

Dates accept `today`, `yesterday`, `-2`, `2026-07-20` — work out "Monday" or "last week" yourself and pass the date.

## Workflow

1. Run the helper (once per change).
2. **Sync** — the app only sees it after a push to `main`:

   ```bash
   cd /Users/oscar/Documents/claude-projects/p100k-data && git pull --rebase --quiet \
     && git add data.json \
     && git commit -m "p100k: <what changed>" \
     && git push
   ```

   Pull **before** editing too if the app may have written since — `git -C /Users/oscar/Documents/claude-projects/p100k-data pull --rebase`.
3. Confirm in a few words — `Done — 8 km logged for today`. No JSON dumps.

## Notes

- Pace accepts `5:20`, `5.20` or `520`; it is stored as seconds and shown as mm:ss.
- `log` amends rather than replaces: omitted fields keep their current value. `--add` adds to the existing km instead of overwriting.
- A day with 0 km, no pace and no pram flag is deleted — same rule the app uses.
- The app pushes its whole local state and resolves per key by `meta` timestamp, so a change here survives the next app sync. Let the app sync once after.
- This skill touches `days`, `settings.raceDate` and their `meta` keys only.
