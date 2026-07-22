#!/usr/bin/env python3
"""Read and write TODAY, ALLEGEDLY — the daily planner (p100k-data/data.json).

Two objects:
  plan[<blockId>] = {id, title, start:"HH:MM", dur:<minutes>, note, icon, color,
                     rep:"once|daily|weekdays|weekends|custom", days:[0-6],
                     date:"YYYY-MM-DD" (only for rep=once), ts}
  plog["YYYY-MM-DD"][<blockId>] = epoch ms the block was ticked

A block is the repeating template; the log is what actually happened that day.
Meta keys: '_pl_<blockId>' for the block, '_pd_<date>' for one day's ticks.

Subcommands: day, blocks, add, edit, rm, tick, untick, stats.
"""
import argparse
import json
import os
import random
import string
import sys
import time
from datetime import date, datetime, timedelta

ALPHA = "0123456789abcdefghijklmnopqrstuvwxyz"
REPS = ("once", "daily", "weekdays", "weekends", "custom")
DAY_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
COLORS = ["#8b5cf6", "#6366f1", "#22d3ee", "#34d399", "#fbbf24", "#fb923c", "#fb7185", "#f472b6"]


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def die(msg, code=2):
    print("error: " + msg, file=sys.stderr)
    raise SystemExit(code)


def b36(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = ALPHA[r] + s
    return s or "0"


def gen_id() -> str:
    """'e' + base36(ms) + 1 random char — the shape the app writes."""
    return "e" + b36(int(time.time() * 1000)) + random.choice(string.ascii_lowercase + string.digits)


def resolve_data_path(explicit: str) -> str:
    if explicit:
        return explicit
    candidates = []
    env = os.environ.get("P100K_DATA")
    if env:
        candidates.append(env)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
    candidates.append(os.path.join(os.path.dirname(repo_root), "p100k-data", "data.json"))
    candidates.append(os.path.expanduser("~/p100k-data/data.json"))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return next((c for c in candidates if c), os.path.expanduser("~/p100k-data/data.json"))


def load(path: str):
    if not os.path.exists(path):
        die(f"data.json not found at {path}", 1)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("plan", {})
    d.setdefault("plog", {})
    d.setdefault("meta", {})
    return d


def save(path: str, d):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


def touch(d, key):
    d["meta"][key] = int(time.time() * 1000)


def parse_date(s: str) -> str:
    s = (s or "today").strip().lower()
    today = date.today()
    if s == "today":
        return today.isoformat()
    if s == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    if s == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if s and s[0] in "+-" and s[1:].isdigit():
        return (today + timedelta(days=int(s))).isoformat()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        die(f"'{s}' is not a date (use YYYY-MM-DD, today, yesterday, -2)")


def parse_hhmm(s: str) -> str:
    s = str(s or "").strip().lower().replace(".", ":")
    ampm = ""
    for suf in ("am", "pm"):
        if s.endswith(suf):
            ampm, s = suf, s[:-2].strip()
    if ":" in s:
        h, _, m = s.partition(":")
    else:
        h, m = (s[:-2], s[-2:]) if len(s) > 2 else (s, "0")
    if not (h.isdigit() and m.isdigit()):
        die(f"'{s}' is not a time (use HH:MM)")
    h, m = int(h), int(m)
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= m < 60):
        die(f"'{s}' is not a valid time")
    return f"{h:02d}:{m:02d}"


def mins(hhmm: str) -> int:
    p = str(hhmm or "09:00").split(":")
    return (int(p[0]) if p[0].isdigit() else 0) * 60 + (int(p[1]) if len(p) > 1 and p[1].isdigit() else 0)


def parse_days(s: str):
    """'mon,wed,fri' or '1,3,5' -> [1,3,5] (0 = Sunday, matching JS getDay)."""
    outv = []
    for part in str(s or "").replace(" ", "").split(","):
        if not part:
            continue
        key = part[:3].lower()
        if key in DAY_NAMES:
            outv.append(DAY_NAMES[key])
        elif part.isdigit() and 0 <= int(part) <= 6:
            outv.append(int(part))
        else:
            die(f"'{part}' is not a weekday (mon…sun or 0–6, 0 = Sunday)")
    return sorted(set(outv))


def on_day(ev, ds: str) -> bool:
    """Mirrors plOnDay(): which days a block lands on."""
    wd = (datetime.strptime(ds, "%Y-%m-%d").date().weekday() + 1) % 7  # 0 = Sunday
    rep = ev.get("rep", "once")
    if rep == "daily":
        return True
    if rep == "weekdays":
        return 1 <= wd <= 5
    if rep == "weekends":
        return wd in (0, 6)
    if rep == "custom":
        return wd in (ev.get("days") or [])
    return ev.get("date") == ds


def events_on(d, ds):
    evs = [ev for ev in d["plan"].values() if ev and on_day(ev, ds)]
    return sorted(evs, key=lambda ev: (mins(ev.get("start")), ev.get("dur") or 30))


def state_of(d, ev, ds):
    """Mirrors plState(): done / miss / now / soon."""
    if (d["plog"].get(ds) or {}).get(ev["id"]):
        return "done"
    today = date.today().isoformat()
    if ds < today:
        return "miss"
    if ds > today:
        return "soon"
    now = datetime.now().hour * 60 + datetime.now().minute
    s = mins(ev.get("start"))
    e = s + (ev.get("dur") or 30)
    if now >= e:
        return "miss"
    if now >= s:
        return "now"
    return "soon"


def block_view(d, ev, ds=None):
    v = {"id": ev["id"], "title": ev.get("title", ""), "start": ev.get("start", ""),
         "dur": ev.get("dur", 30), "end": "", "rep": ev.get("rep", "once"),
         "days": ev.get("days") or [], "date": ev.get("date", ""),
         "icon": ev.get("icon", ""), "note": ev.get("note", "")}
    end = mins(ev.get("start")) + (ev.get("dur") or 30)
    v["end"] = f"{(end // 60) % 24:02d}:{end % 60:02d}"
    if ds:
        v["state"] = state_of(d, ev, ds)
        at = (d["plog"].get(ds) or {}).get(ev["id"])
        v["ticked_at"] = datetime.fromtimestamp(at / 1000).strftime("%H:%M") if at else ""
    return v


def find_block(d, ref, at=None):
    """Match by exact id, then by title substring.

    Two blocks can share a title ("Gym" at 07:30 and at 18:00), so ticking takes
    an `at` minute-of-day hint: the block whose window covers that moment wins,
    else the most recent one already started. Still tied — error, listing times,
    so the next attempt can name one exactly."""
    if ref in d["plan"]:
        return d["plan"][ref]
    q = str(ref).strip().lower()
    hits = [ev for ev in d["plan"].values() if q and q in ev.get("title", "").lower()]
    if not hits:
        die(f"no block matches '{ref}'", 1)
    if len(hits) == 1:
        return hits[0]
    if at is not None:
        inside = [e for e in hits if mins(e.get("start")) <= at < mins(e.get("start")) + (e.get("dur") or 30)]
        if len(inside) == 1:
            return inside[0]
        started = [e for e in hits if mins(e.get("start")) <= at]
        if started:
            return max(started, key=lambda e: mins(e.get("start")))
        return min(hits, key=lambda e: mins(e.get("start")))
    die("'%s' matches %d blocks: %s — name one by id or time"
        % (ref, len(hits), ", ".join(f"{e.get('title')} at {e.get('start')} ({e['id']})" for e in hits)), 1)


def cmd_day(d, a):
    ds = parse_date(a.date)
    rows = [block_view(d, ev, ds) for ev in events_on(d, ds)]
    out({"cmd": "day", "date": ds, "count": len(rows), "blocks": rows})


def cmd_blocks(d, a):
    rows = [block_view(d, ev) for ev in sorted(d["plan"].values(), key=lambda e: mins(e.get("start")))]
    out({"cmd": "blocks", "count": len(rows), "blocks": rows})


def apply_fields(d, ev, a, creating):
    if a.title is not None:
        ev["title"] = a.title.strip()
    if a.start is not None:
        ev["start"] = parse_hhmm(a.start)
    if a.dur is not None:
        ev["dur"] = max(5, min(int(a.dur), 720))
    if a.note is not None:
        ev["note"] = a.note.strip()
    if a.icon is not None:
        ev["icon"] = a.icon.strip()
    if a.color is not None:
        c = a.color.strip()
        ev["color"] = c if c.startswith("#") else COLORS[abs(hash(c)) % len(COLORS)]
    if a.rep is not None:
        if a.rep not in REPS:
            die("--rep must be one of " + ", ".join(REPS))
        ev["rep"] = a.rep
    if a.days is not None:
        ev["days"] = parse_days(a.days)
        if ev["days"] and (a.rep is None or a.rep == "custom"):
            ev["rep"] = "custom"
    if a.on is not None:
        ev["date"] = parse_date(a.on)
        if a.rep is None:
            ev["rep"] = "once"
    if ev.get("rep") == "once" and not ev.get("date"):
        ev["date"] = date.today().isoformat()
    if ev.get("rep") == "custom" and not ev.get("days"):
        die("rep=custom needs --days (e.g. --days mon,wed,fri)")
    ev["ts"] = int(time.time() * 1000)
    return ev


def cmd_add(d, a):
    if not (a.title or "").strip():
        die("--title is required")
    bid = gen_id()
    while bid in d["plan"]:
        bid = gen_id()
    ev = {"id": bid, "title": "", "start": "09:00", "dur": 30, "note": "", "icon": "🎯",
          "color": COLORS[len(d["plan"]) % len(COLORS)], "rep": "once", "days": [], "date": ""}
    apply_fields(d, ev, a, True)
    d["plan"][bid] = ev
    touch(d, "_pl_" + bid)
    out({"cmd": "add", "block": block_view(d, ev)})


def cmd_edit(d, a):
    ev = find_block(d, a.ref)
    apply_fields(d, ev, a, False)
    touch(d, "_pl_" + ev["id"])
    out({"cmd": "edit", "block": block_view(d, ev)})


def cmd_rm(d, a):
    ev = find_block(d, a.ref)
    d["plan"].pop(ev["id"], None)
    for ds in list(d["plog"].keys()):
        if d["plog"][ds].pop(ev["id"], None) is not None:
            touch(d, "_pd_" + ds)
    touch(d, "_pl_" + ev["id"])
    out({"cmd": "rm", "removed": ev["id"], "title": ev.get("title", "")})


def cmd_tick(d, a):
    ds = parse_date(a.date)
    hint = mins(parse_hhmm(a.at)) if a.at else (datetime.now().hour * 60 + datetime.now().minute)
    ev = find_block(d, a.ref, at=hint)
    when = int(time.time() * 1000)
    if a.at:
        hh, mm = parse_hhmm(a.at).split(":")
        dt = datetime.strptime(ds, "%Y-%m-%d").replace(hour=int(hh), minute=int(mm))
        when = int(dt.timestamp() * 1000)
    d["plog"].setdefault(ds, {})[ev["id"]] = when
    touch(d, "_pd_" + ds)
    out({"cmd": "tick", "date": ds, "block": block_view(d, ev, ds)})


def cmd_untick(d, a):
    ds = parse_date(a.date)
    # prefer the blocks actually ticked that day; never guess between two of them,
    # because guessing wrong throws away a tick silently
    q = str(a.ref).strip().lower()
    ticked = [e for e in d["plan"].values()
              if (d["plog"].get(ds) or {}).get(e["id"]) and q in e.get("title", "").lower()]
    if len(ticked) == 1:
        ev = ticked[0]
    elif len(ticked) > 1:
        die("'%s' matches %d ticked blocks: %s — name one by id or time"
            % (a.ref, len(ticked), ", ".join(f"{e.get('title')} at {e.get('start')} ({e['id']})"
                                             for e in ticked)), 1)
    else:
        ev = find_block(d, a.ref)
    had = (d["plog"].get(ds) or {}).pop(ev["id"], None) is not None
    if not d["plog"].get(ds):
        d["plog"].pop(ds, None)
    touch(d, "_pd_" + ds)
    out({"cmd": "untick", "date": ds, "was_ticked": had, "block": block_view(d, ev, ds)})


PL_SEED = [
    ("Up, feet on the floor", "07:30", 30, "💤", "#fbbf24", "daily"),
    ("Breakfast and coffee", "08:00", 30, "☕", "#fb923c", "daily"),
    ("The hard thing, first", "09:00", 90, "🎯", "#8b5cf6", "weekdays"),
    ("Move — walk or run", "12:00", 45, "🏃", "#34d399", "daily"),
    ("Lunch, away from screens", "13:00", 45, "🍽", "#22d3ee", "daily"),
    ("Admin and email", "16:00", 45, "💼", "#6366f1", "weekdays"),
    ("Dinner", "19:00", 60, "🍽", "#22d3ee", "daily"),
    ("Wind down, screens off", "22:30", 30, "🧘", "#fb7185", "daily"),
]


def cmd_seed(d, a):
    """The app's 'start with an ordinary day' — refuses to run over an existing plan."""
    if d["plan"] and not a.force:
        die("there are already %d blocks — pass --force to add the ordinary day on top"
            % len(d["plan"]), 1)
    base = int(time.time() * 1000)
    added = []
    for i, (title, start, dur, icon, color, rep) in enumerate(PL_SEED):
        bid = "e" + b36(base) + str(i)
        d["plan"][bid] = {"id": bid, "title": title, "start": start, "dur": dur, "note": "",
                          "icon": icon, "color": color, "rep": rep, "days": [], "date": "",
                          "ts": base + i}
        touch(d, "_pl_" + bid)
        added.append(block_view(d, d["plan"][bid]))
    out({"cmd": "seed", "added": len(added), "blocks": added})


def cmd_copy(d, a):
    """Duplicate a block — same shape, new id, optionally re-timed or re-dated."""
    src = find_block(d, a.ref)
    bid = gen_id()
    while bid in d["plan"]:
        bid = gen_id()
    ev = dict(src)
    ev["id"] = bid
    ev["days"] = list(src.get("days") or [])
    if a.title is None:
        a.title = src.get("title", "")
    apply_fields(d, ev, a, True)
    d["plan"][bid] = ev
    touch(d, "_pl_" + bid)
    out({"cmd": "copy", "from": src["id"], "block": block_view(d, ev)})


def cmd_clear(d, a):
    """Wipe one day's ticks, or every block that lands on it."""
    ds = parse_date(a.date)
    ticks = len(d["plog"].get(ds) or {})
    d["plog"].pop(ds, None)
    touch(d, "_pd_" + ds)
    removed = []
    if a.blocks:
        for ev in events_on(d, ds):
            d["plan"].pop(ev["id"], None)
            touch(d, "_pl_" + ev["id"])
            removed.append(ev.get("title", ""))
    out({"cmd": "clear", "date": ds, "ticks_cleared": ticks, "blocks_removed": removed})


def cmd_stats(d, a):
    ds = parse_date(a.date)
    rows = [block_view(d, ev, ds) for ev in events_on(d, ds)]
    done = sum(1 for r in rows if r["state"] == "done")
    miss = sum(1 for r in rows if r["state"] == "miss")
    left = len(rows) - done - miss
    out({"cmd": "stats", "date": ds, "total": len(rows), "did_it": done,
         "missed": miss, "still_to_go": left,
         "pct": round(done / len(rows) * 100) if rows else 0})


WRITES = {"add", "edit", "rm", "tick", "untick", "seed", "copy", "clear"}


def add_field_args(p, with_title_flag=True):
    if with_title_flag:
        p.add_argument("--title", default=None)
    p.add_argument("--start", default=None, help="HH:MM (also 7pm, 0730)")
    p.add_argument("--dur", type=int, default=None, help="minutes, 5–720")
    p.add_argument("--note", default=None)
    p.add_argument("--icon", default=None, help="one emoji")
    p.add_argument("--color", default=None, help="#rrggbb")
    p.add_argument("--rep", default=None, choices=list(REPS))
    p.add_argument("--days", default=None, help="for rep=custom: mon,wed,fri or 1,3,5")
    p.add_argument("--on", default=None, help="for rep=once: the date it happens")


def build_parser():
    ap = argparse.ArgumentParser(description="Read/write TODAY, ALLEGEDLY — the daily planner.")
    ap.add_argument("--data", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("day", help="one day's blocks with their state"); p.set_defaults(fn=cmd_day)
    p.add_argument("date", nargs="?", default="today")

    sub.add_parser("blocks", help="every block in the plan").set_defaults(fn=cmd_blocks)

    p = sub.add_parser("add", help="add a block"); p.set_defaults(fn=cmd_add)
    add_field_args(p)

    p = sub.add_parser("edit", help="change a block"); p.set_defaults(fn=cmd_edit)
    p.add_argument("ref", help="block id or title substring")
    add_field_args(p)

    p = sub.add_parser("rm", help="delete a block and its ticks"); p.set_defaults(fn=cmd_rm)
    p.add_argument("ref")

    p = sub.add_parser("tick", help="mark a block done"); p.set_defaults(fn=cmd_tick)
    p.add_argument("ref"); p.add_argument("--date", default="today")
    p.add_argument("--at", default="", help="HH:MM it was actually done")

    p = sub.add_parser("untick", help="undo a tick"); p.set_defaults(fn=cmd_untick)
    p.add_argument("ref"); p.add_argument("--date", default="today")

    p = sub.add_parser("stats", help="did it / missed / still to go"); p.set_defaults(fn=cmd_stats)
    p.add_argument("date", nargs="?", default="today")

    p = sub.add_parser("seed", help="fill an empty plan with an ordinary day")
    p.set_defaults(fn=cmd_seed)
    p.add_argument("--force", action="store_true", help="add it even if blocks exist")

    p = sub.add_parser("copy", help="duplicate a block"); p.set_defaults(fn=cmd_copy)
    p.add_argument("ref")
    add_field_args(p)

    p = sub.add_parser("clear", help="wipe a day's ticks (--blocks also deletes its blocks)")
    p.set_defaults(fn=cmd_clear)
    p.add_argument("date", nargs="?", default="today")
    p.add_argument("--blocks", action="store_true")

    return ap


def main() -> int:
    a = build_parser().parse_args()
    path = resolve_data_path(a.data)
    d = load(path)
    for f in ("title", "start", "dur", "note", "icon", "color", "rep", "days", "on"):
        if not hasattr(a, f):
            setattr(a, f, None)
    a.fn(d, a)
    if a.cmd in WRITES:
        save(path, d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
