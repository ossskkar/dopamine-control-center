#!/usr/bin/env python3
"""Read and write the PROJECT 100K running log (p100k-data/data.json).

The app keeps one entry per calendar day under the top-level "days" object.
A day is either a plain km number (legacy) or {km, sp[, baby]} where sp is the
pace in seconds per km and baby means the run happened pushing the pram. The
race date lives in settings.raceDate; the 14-week plan is derived from it.

Every write mirrors the app's own setDay() byte for byte and stamps the matching
meta timestamp ('<date>' for a day, '_race' for the race date) so the app adopts
this version on its next sync instead of overwriting it.

Subcommands: log, rm, days, week, summary, race.
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

# The 14-week plan, copied from app.html (PLAN). vol = planned km that week.
PLAN = [
    (1, "Rebuild", 30, 15), (2, "Rebuild", 36, 18), (3, "Rebuild", 42, 24),
    (4, "Cutback", 30, 16), (5, "Ultra block", 48, 28), (6, "Ultra block", 54, 32),
    (7, "Cutback", 38, 20), (8, "Ultra block", 58, 36), (9, "Ultra block", 62, 40),
    (10, "Cutback", 44, 24), (11, "Peak", 68, 58), (12, "Recover", 46, 26),
    (13, "Taper", 32, 18), (14, "RACE", 111, 100),
]


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


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
        print(f"error: data.json not found at {path}", file=sys.stderr)
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("days", {})
    d.setdefault("meta", {})
    d.setdefault("settings", {})
    return d


def save(path: str, d):
    """The app writes compact JSON with no trailing newline — match it exactly."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


def touch(d, key):
    d["meta"][key] = int(time.time() * 1000)


def parse_date(s: str) -> str:
    """today / yesterday / tomorrow / -2 / +1 / YYYY-MM-DD."""
    s = (s or "today").strip().lower()
    today = date.today()
    if s == "today":
        return today.isoformat()
    if s == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    if s == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if s and (s[0] in "+-") and s[1:].isdigit():
        return (today + timedelta(days=int(s))).isoformat()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        print(f"error: '{s}' is not a date (use YYYY-MM-DD, today, yesterday, -2)", file=sys.stderr)
        raise SystemExit(2)


def parse_pace(s) -> int:
    """'5:20' / '5.20' / '520' / '5' -> seconds per km. Mirrors the app."""
    s = str(s or "").strip()
    if not s:
        return 0
    for sep in (":", ".", ","):
        if sep in s:
            a, _, b = s.partition(sep)
            if a.isdigit() and b.isdigit():
                return int(a) * 60 + min(int((b + "0")[:2]), 59)
            return 0
    if not s.isdigit():
        return 0
    if len(s) <= 2:
        return int(s) * 60
    return int(s[:-2]) * 60 + min(int(s[-2:]), 59)


def fmt_pace(sec) -> str:
    if not sec:
        return ""
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def km_of(v):
    return (v.get("km") or 0) if isinstance(v, dict) else (v or 0)


def sp_of(v):
    s = v.get("sp") if isinstance(v, dict) else None
    return s if (s or 0) > 0 else None


def baby_of(v):
    return bool(isinstance(v, dict) and v.get("baby"))


def write_day(d, ds, km, sp, baby):
    """Exactly the shape setDay() writes: delete / {km,sp[,baby]} / plain number."""
    days = d["days"]
    km = int(round(km or 0))
    if km <= 0 and not (sp and sp > 0) and not baby:
        days.pop(ds, None)
    elif (sp and sp > 0) or baby:
        v = {"km": km, "sp": sp if (sp and sp > 0) else None}
        if baby:
            v["baby"] = 1
        days[ds] = v
    else:
        days[ds] = km
    touch(d, ds)
    return days.get(ds)


def day_view(ds, v):
    return {"date": ds, "km": km_of(v), "pace": fmt_pace(sp_of(v)),
            "sp": sp_of(v), "baby": baby_of(v)}


# --- plan geometry: PLAN_START = Monday of race week, minus 13 weeks ---
def plan_start(d) -> date:
    rd = d["settings"].get("raceDate") or "2026-10-17"
    race = datetime.strptime(rd, "%Y-%m-%d").date()
    monday = race - timedelta(days=race.weekday())
    return monday - timedelta(weeks=13)


def week_dates(d, w):
    """w is 1-based, matching the plan table."""
    mon = plan_start(d) + timedelta(weeks=w - 1)
    return [(mon + timedelta(days=i)).isoformat() for i in range(7)]


def current_week(d) -> int:
    idx = (date.today() - plan_start(d)).days // 7
    return min(max(idx, 0), 13) + 1


def cmd_log(d, a):
    ds = parse_date(a.date)
    cur = d["days"].get(ds)
    km = km_of(cur) if a.km is None else a.km
    if a.add and a.km is not None:
        km = km_of(cur) + a.km
    sp = sp_of(cur)
    if a.pace:
        sp = parse_pace(a.pace)
        if not sp:
            print(f"error: --pace '{a.pace}' is not mm:ss", file=sys.stderr)
            raise SystemExit(2)
    if a.no_pace:
        sp = None
    baby = baby_of(cur)
    if a.baby:
        baby = True
    if a.no_baby:
        baby = False
    v = write_day(d, ds, km, sp, baby)
    out({"cmd": "log", "wrote": day_view(ds, v), "removed": v is None})


def cmd_rm(d, a):
    ds = parse_date(a.date)
    had = ds in d["days"]
    d["days"].pop(ds, None)
    touch(d, ds)
    out({"cmd": "rm", "date": ds, "existed": had})


def cmd_days(d, a):
    rows = [day_view(ds, v) for ds, v in sorted(d["days"].items())]
    if a.frm:
        rows = [r for r in rows if r["date"] >= parse_date(a.frm)]
    if a.to:
        rows = [r for r in rows if r["date"] <= parse_date(a.to)]
    if a.last:
        rows = rows[-a.last:]
    out({"cmd": "days", "count": len(rows), "total_km": sum(r["km"] for r in rows), "days": rows})


def cmd_week(d, a):
    w = a.week or current_week(d)
    w = min(max(w, 1), 14)
    num, phase, vol, lr = PLAN[w - 1]
    dates = week_dates(d, w)
    rows = [day_view(ds, d["days"].get(ds)) for ds in dates]
    actual = sum(r["km"] for r in rows)
    paced = [(r["sp"], r["km"]) for r in rows if r["sp"] and r["km"]]
    avg = sum(s * k for s, k in paced) / sum(k for _, k in paced) if paced else 0
    out({"cmd": "week", "week": w, "phase": phase, "planned_km": vol, "long_run_km": lr,
         "actual_km": actual, "left_km": max(vol - actual, 0), "avg_pace": fmt_pace(avg),
         "monday": dates[0], "sunday": dates[6], "days": rows})


def cmd_summary(d, a):
    banked = sum(km_of(v) for v in d["days"].values())
    total_plan = sum(p[2] for p in PLAN)
    race = d["settings"].get("raceDate", "")
    to_race = (datetime.strptime(race, "%Y-%m-%d").date() - date.today()).days if race else None
    logged = sorted(d["days"].keys())
    longest = max((km_of(v) for v in d["days"].values()), default=0)
    # current streak of consecutive days with any km, counting back from today
    streak, cur = 0, date.today()
    while km_of(d["days"].get(cur.isoformat())) > 0:
        streak += 1
        cur -= timedelta(days=1)
    w = current_week(d)
    out({"cmd": "summary", "banked_km": banked, "plan_total_km": total_plan,
         "pct": round(banked / total_plan * 100, 1) if total_plan else 0,
         "race_date": race, "days_to_race": to_race,
         "current_week": w, "week_phase": PLAN[w - 1][1], "week_planned_km": PLAN[w - 1][2],
         "week_actual_km": sum(km_of(d["days"].get(ds)) for ds in week_dates(d, w)),
         "days_logged": len(logged), "first_day": logged[0] if logged else "",
         "last_day": logged[-1] if logged else "", "longest_run_km": longest,
         "current_streak_days": streak})


def cmd_race(d, a):
    if a.set:
        ds = parse_date(a.set)
        d["settings"]["raceDate"] = ds
        touch(d, "_race")
        out({"cmd": "race", "set": ds, "days_away": (datetime.strptime(ds, "%Y-%m-%d").date() - date.today()).days})
    else:
        ds = d["settings"].get("raceDate", "")
        away = (datetime.strptime(ds, "%Y-%m-%d").date() - date.today()).days if ds else None
        out({"cmd": "race", "race_date": ds, "days_away": away, "plan_start": plan_start(d).isoformat()})


WRITES = {"log", "rm", "race"}


def build_parser():
    ap = argparse.ArgumentParser(description="Read/write the PROJECT 100K running log.")
    ap.add_argument("--data", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("log", help="record or amend one day's run")
    p.set_defaults(fn=cmd_log)
    p.add_argument("--date", default="today")
    p.add_argument("--km", type=float, default=None)
    p.add_argument("--add", action="store_true", help="add --km to what's already logged")
    p.add_argument("--pace", default="", help="mm:ss per km, e.g. 5:20")
    p.add_argument("--no-pace", action="store_true")
    p.add_argument("--baby", action="store_true", help="ran with the pram")
    p.add_argument("--no-baby", action="store_true")

    p = sub.add_parser("rm", help="delete a day"); p.set_defaults(fn=cmd_rm)
    p.add_argument("--date", default="today")

    p = sub.add_parser("days", help="list logged days"); p.set_defaults(fn=cmd_days)
    p.add_argument("--from", dest="frm", default="")
    p.add_argument("--to", default="")
    p.add_argument("--last", type=int, default=0)

    p = sub.add_parser("week", help="plan vs actual for a plan week"); p.set_defaults(fn=cmd_week)
    p.add_argument("week", nargs="?", type=int, default=0)

    sub.add_parser("summary", help="banked km, streak, race countdown").set_defaults(fn=cmd_summary)

    p = sub.add_parser("race", help="show or set the race date"); p.set_defaults(fn=cmd_race)
    p.add_argument("--set", default="")

    return ap


def main() -> int:
    a = build_parser().parse_args()
    path = resolve_data_path(a.data)
    d = load(path)
    a.fn(d, a)
    if a.cmd in WRITES:
        save(path, d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
