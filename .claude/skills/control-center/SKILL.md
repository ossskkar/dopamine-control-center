---
name: control-center
description: Cross-system control for the Dopamine Control Center — the day's brief across every system, syncing the data repo (pull before edits, push after), the hub tile order, and diagnosing sync problems. Use for "what's on today", "what have I got on", "what's the state of everything", "sync my data", "push that to the app", "put the planner tile first", "the app isn't showing my change", "is the data healthy". The other skills own one system each: project-100k (runs), today-allegedly (planner), mission-eventually / add-todo / board-query (to-dos), flying-dutch (Dutch exams).
---

# control-center

The layer above the individual systems: the data repo itself, the hub tile order, and a cross-system overview.

## How the data flows

The app (`index.html`, GitHub Pages) keeps everything in localStorage and mirrors it to the private repo **`p100k-data`**, file `data.json`, branch **`main`**, via the GitHub Contents API. Skills edit that same file in the local clone at `../p100k-data`.

Merging is per-key last-write-wins on `meta` timestamps, so:

1. **Pull before editing** — the app may have written since.
2. Edit through a system skill (each stamps the right `meta` key).
3. **Push to `main`** — nothing else makes the app see it.
4. The app adopts the change on its next sync; hard-reload the page if it looks stale.

## Driving it

```bash
C=".claude/skills/control-center/dcc.py"

python3 $C brief                  # "what's on today?" — plan, to-dos due, run, next exam
python3 $C brief --date 2026-07-25
python3 $C status                 # every system's counts + git state of the data repo
python3 $C pull                   # git pull --rebase in p100k-data
python3 $C push -m "plan: add gym block"
python3 $C doctor                 # clone, branch, ahead/behind, JSON shape, missing timestamps

python3 $C hub                    # current tile order
python3 $C hub-set plan,todo,p100k,oranje,diary,money
python3 $C hub-move p100k --to 1
```

Tile ids: `p100k`, `plan`, `todo`, `oranje`, `money`, `diary`.

## Notes

- If the clone is missing: `gh repo clone ossskkar/p100k-data ../p100k-data` (private repo, needs the GitHub login).
- `data.json` is compact single-line JSON. Never reformat it — `doctor` flags it if something did.
- Pushing to any branch other than `main` is invisible to the app.
- Operation Rainy Day and the diary are still shells: reachable tiles with no data model, so no skill can change anything inside them yet.
- This skill only writes `hub` and `meta._hub`; everything else it does is git.
