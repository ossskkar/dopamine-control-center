---
name: flying-dutch
description: Full control over OPERATION FLYING DUTCH — the Dutch inburgering exam system in the Dopamine Control Center (oranje, res, ws and flash in p100k-data/data.json). Use for anything about the six exams (KNM, ONA, Lezen, Luisteren, Spreken, Schrijven): "I booked the reading exam for 12 Sept", "I passed KNM", "ONA is waived", "add this study link to Listening", "I keep mixing up de/het — track it", "how are my flashcards doing", "which exams are left". Covers exam status and dates, study/mock resource lists, the weak-spot list and flashcard deck stats.
---

# flying-dutch

The Dutch exam system: six exams, each with a status, a date, a booking link, two resource lists, a weak-spot list and (for KNM) a flashcard deck.

## Data model (do not reshape it)

`p100k-data/data.json` is compact single-line JSON — never reformat it. Exam ids: `knm`, `ona`, `lezen`, `luisteren`, `spreken`, `schrijven` (the helper also accepts English names — "reading" → `lezen`).

- `oranje[exam]` = `{date, status, reg}` — status is `todo` | `booked` | `passed` | `waived`. `reg` overrides the shipped booking link.
- `res[kind][exam]` = `[{id, title, url, tag, desc}]`, kind `study` | `mock`, tag `official` | `free` | `paid`.
- `ws[exam]` = `[{id, what, cat, note, hits, last}]` — a mistake you keep making; `hits` counts how often it bit you.
- `flash[deck][cardId]` = `{lvl, right, wrong, seen}` — flashcard SRS stats (deck `knm`).
- Meta: `_or_<exam>`, `_res_<kind>_<exam>`, `_ws_<exam>`, `_fl_<deck>`. The helper stamps these.

## Driving it

`REF` = an item's id, its 1-based position, or a substring of its title/what.

```bash
F=".claude/skills/flying-dutch/dutch.py"

# --- exams ---
python3 $F exams                                       # all six: status, date, counts
python3 $F exam-set lezen --status booked --date 2026-09-12
python3 $F exam-set knm --status passed
python3 $F exam-set ona --status waived
python3 $F exam-set spreken --clear-date
python3 $F exam-set lezen --reg https://duo.nl/...     # custom booking link (--reg-default undoes)

# --- resources (study material / mock exams) ---
python3 $F res luisteren                               # both lists; or --kind study
python3 $F res-add luisteren --kind study --title "NT2 Taalmenu" \
        --url nt2taalmenu.nl --tag free --desc "Free A1–B1 exercises"
python3 $F res-edit luisteren "Taalmenu" --kind study --desc "..."
python3 $F res-rm luisteren "Taalmenu" --kind study

# --- weak spots ---
python3 $F ws schrijven                                # worst first
python3 $F ws-add schrijven --what "de/het with abstract nouns" --cat grammar
python3 $F ws-hit schrijven "de/het"                   # it bit me again
python3 $F ws-reset schrijven "de/het"                 # hits back to 0
python3 $F ws-rm schrijven "de/het"

# --- flashcards ---
python3 $F flash                                       # per-deck accuracy, levels, worst cards
python3 $F flash-reset knm                             # wipe deck progress (--card <id> for one)
```

## Saying it in plain language

| What the user says | What to run |
|---|---|
| "I booked reading for 12 September" | `exam-set reading --status booked --date 2026-09-12` |
| "passed KNM" / "ONA doesn't apply to me" | `exam-set knm --status passed` / `exam-set ona --status waived` |
| "the listening exam moved, no date now" | `exam-set luisteren --clear-date` |
| "save this site for writing practice" | `res-add schrijven --kind study --title … --url …` |
| "I keep getting de/het wrong" | `ws-add schrijven --what "de/het" --cat grammar` |
| "that one caught me again" | `ws-hit schrijven "de/het"` |
| "which exams are left?" / "when's the next one?" | `exams` |
| "how are my flashcards going?" | `flash` |

Exams answer to English names ("reading" → `lezen`, "speaking" → `spreken`) as well as their ids.

## Workflow

1. Run the helper (once per change). Convert dates to `YYYY-MM-DD` yourself.
2. **Sync** — the app only sees it after a push to `main`:

   ```bash
   cd /Users/oscar/Documents/claude-projects/p100k-data && git pull --rebase --quiet \
     && git add data.json \
     && git commit -m "oranje: <what changed>" \
     && git push
   ```

   Pull **before** editing too if the app may have written since.
3. Confirm in a few words — `Done — Lezen booked for 12 Sept`. No JSON dumps.

## Notes

- `waived` means the exam does not apply (ONA is currently waived) — it counts as done in the app's timeline.
- `flash-reset` cannot be undone and throws away real study history; confirm before running it.
- The flashcard *cards* themselves live in the app (`DECKS` in app.html), not in the data file — this skill only reads and resets their stats.
- This skill touches `oranje`, `res`, `ws`, `flash` and their `meta` keys only.
