#!/usr/bin/env python3
"""Cross-system control for the Dopamine Control Center data (p100k-data).

Does the things that are not one system's business:
  status   what every system currently holds, plus the data repo's git state
  pull     git pull --rebase in p100k-data (do this before editing)
  push     git add/commit/push data.json (do this after editing)
  hub      the order of the hub tiles
  hub-set  reorder them
  doctor   check the clone, the remote, the meta timestamps and the JSON shape

Tile ids: p100k, plan, todo, oranje, money, diary.
Meta key for the tile order is '_hub'.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime

TILES = {
    "p100k": "Project 100K (running)",
    "plan": "Today, Allegedly (daily planner)",
    "todo": "Mission: Eventually (to-dos)",
    "oranje": "Operation Flying Dutch (Dutch exams)",
    "money": "Operation Rainy Day (finance — shell, no data yet)",
    "diary": "A Very Unexamined Life (diary — shell, no data yet)",
}


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def die(msg, code=2):
    print("error: " + msg, file=sys.stderr)
    raise SystemExit(code)


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
        die(f"data.json not found at {path} — clone it: "
            f"gh repo clone ossskkar/p100k-data {os.path.dirname(path)}", 1)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("meta", {})
    return d


def save(path: str, d):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


def git(repo, *args, check=False):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True)
    if check and p.returncode:
        die((p.stderr or p.stdout).strip() or f"git {' '.join(args)} failed", 1)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def ago(ms):
    if not ms:
        return ""
    secs = time.time() - ms / 1000
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= n:
            return f"{int(secs // n)}{unit} ago"
    return "just now"


def cmd_status(d, a, path):
    repo = os.path.dirname(path)
    _, branch, _ = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _, last, _ = git(repo, "log", "-1", "--format=%h %ad %s", "--date=iso")
    _, dirty, _ = git(repo, "status", "--porcelain")
    plan_days = d.get("plog", {})
    newest = max(d["meta"].values()) if d["meta"] else 0
    out({"cmd": "status", "data": path, "branch": branch, "last_commit": last,
         "uncommitted": bool(dirty), "last_write": ago(newest),
         "systems": {
             "p100k": {"days_logged": len(d.get("days", {})),
                       "total_km": sum((v.get("km") or 0) if isinstance(v, dict) else (v or 0)
                                       for v in d.get("days", {}).values()),
                       "race_date": d.get("settings", {}).get("raceDate", "")},
             "todo": {"projects": len(d.get("todo", {})),
                      "tasks": sum(len(p.get("tasks", [])) for p in d.get("todo", {}).values())},
             "plan": {"blocks": len(d.get("plan", {})), "days_with_ticks": len(plan_days)},
             "oranje": {"exams_done": sum(1 for v in d.get("oranje", {}).values()
                                          if v.get("status") in ("passed", "waived")),
                        "weak_spots": sum(len(v) for v in d.get("ws", {}).values()),
                        "flash_decks": list(d.get("flash", {}).keys())},
             "money": "shell — no data model yet",
             "diary": "shell — no data model yet"},
         "hub_order": d.get("hub", [])})


def _on_day(ev, ds):
    """Same rule as the planner: which days a block lands on."""
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


def cmd_brief(d, a, path):
    """One answer to 'what's on today' — every system, one day."""
    ds = a.date or date.today().isoformat()
    now = datetime.now().hour * 60 + datetime.now().minute
    ticks = d.get("plog", {}).get(ds) or {}
    blocks = []
    for ev in sorted((e for e in d.get("plan", {}).values() if _on_day(e, ds)),
                     key=lambda e: e.get("start", "")):
        p = str(ev.get("start", "0:0")).split(":")
        s = (int(p[0]) if p[0].isdigit() else 0) * 60 + (int(p[1]) if len(p) > 1 and p[1].isdigit() else 0)
        e_ = s + (ev.get("dur") or 30)
        today = date.today().isoformat()
        state = ("done" if ticks.get(ev["id"]) else
                 "miss" if (ds < today or (ds == today and now >= e_)) else
                 "soon" if (ds > today or now < s) else "now")
        blocks.append({"start": ev.get("start"), "title": ev.get("title"), "state": state})
    due, overdue = [], []
    for p in d.get("todo", {}).values():
        for t in p.get("tasks", []):
            if t.get("done") or not t.get("due"):
                continue
            row = {"title": t.get("title"), "project": p.get("name"), "due": t["due"]}
            if t["due"] == ds:
                due.append(row)
            elif t["due"] < ds:
                overdue.append(row)
    run = d.get("days", {}).get(ds)
    exams = [{"exam": k, "date": v.get("date"), "status": v.get("status")}
             for k, v in d.get("oranje", {}).items()
             if v.get("date") and v.get("status") not in ("passed", "waived") and v["date"] >= ds]
    race = d.get("settings", {}).get("raceDate", "")
    out({"cmd": "brief", "date": ds,
         "plan": {"blocks": blocks,
                  "did_it": sum(1 for b in blocks if b["state"] == "done"),
                  "missed": sum(1 for b in blocks if b["state"] == "miss"),
                  "still_to_go": sum(1 for b in blocks if b["state"] in ("now", "soon"))},
         "todos": {"due_today": due, "overdue": sorted(overdue, key=lambda r: r["due"])},
         "run": {"km": (run.get("km") if isinstance(run, dict) else run) or 0} if run else None,
         "next_exam": sorted(exams, key=lambda e: e["date"])[0] if exams else None,
         "days_to_race": (datetime.strptime(race, "%Y-%m-%d").date()
                          - datetime.strptime(ds, "%Y-%m-%d").date()).days if race else None})


def cmd_pull(d, a, path):
    repo = os.path.dirname(path)
    code, so, se = git(repo, "pull", "--rebase")
    out({"cmd": "pull", "ok": code == 0, "output": so or se})
    if code:
        raise SystemExit(1)


def cmd_push(d, a, path):
    repo = os.path.dirname(path)
    _, dirty, _ = git(repo, "status", "--porcelain")
    if not dirty:
        out({"cmd": "push", "ok": True, "note": "nothing to commit"})
        return
    git(repo, "add", "data.json", check=True)
    msg = a.message or ("dcc: update " + date.today().isoformat())
    git(repo, "commit", "-m", msg, check=True)
    code, so, se = git(repo, "push")
    out({"cmd": "push", "ok": code == 0, "message": msg, "output": so or se})
    if code:
        raise SystemExit(1)


def cmd_hub(d, a, path):
    order = d.get("hub") or list(TILES)
    out({"cmd": "hub", "order": [{"pos": i + 1, "id": t, "what": TILES.get(t, "?")}
                                 for i, t in enumerate(order)]})


def apply_hub(d, order):
    d["hub"] = order
    d["meta"]["_hub"] = int(time.time() * 1000)


def cmd_hub_set(d, a, path):
    ids = [t.strip() for t in a.order.replace(" ", ",").split(",") if t.strip()]
    bad = [t for t in ids if t not in TILES]
    if bad:
        die(f"unknown tile(s): {', '.join(bad)} (valid: {', '.join(TILES)})")
    order = ids + [t for t in (d.get("hub") or list(TILES)) if t not in ids]
    order += [t for t in TILES if t not in order]
    apply_hub(d, order)
    out({"cmd": "hub-set", "order": order})


def cmd_hub_move(d, a, path):
    if a.tile not in TILES:
        die(f"unknown tile '{a.tile}' (valid: {', '.join(TILES)})")
    order = [t for t in (d.get("hub") or list(TILES)) if t in TILES]
    order += [t for t in TILES if t not in order]
    order.remove(a.tile)
    pos = min(max(a.to, 1), len(order) + 1) - 1
    order.insert(pos, a.tile)
    apply_hub(d, order)
    out({"cmd": "hub-move", "order": order})


def cmd_doctor(d, a, path):
    repo = os.path.dirname(path)
    problems = []
    code, remote, _ = git(repo, "remote", "get-url", "origin")
    if code:
        problems.append("p100k-data has no origin remote")
    _, branch, _ = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        problems.append(f"data repo is on '{branch}' — the app reads main, so pushes elsewhere are invisible")
    git(repo, "fetch", "--quiet")
    _, behind, _ = git(repo, "rev-list", "--count", "HEAD..@{u}")
    _, ahead, _ = git(repo, "rev-list", "--count", "@{u}..HEAD")
    if behind and behind != "0":
        problems.append(f"{behind} commit(s) behind the remote — run pull before editing")
    if ahead and ahead != "0":
        problems.append(f"{ahead} commit(s) ahead — run push so the app can see them")
    _, dirty, _ = git(repo, "status", "--porcelain")
    if dirty:
        problems.append("uncommitted changes in the data repo")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if raw.endswith("\n") or "\n" in raw:
        problems.append("data.json is not single-line compact JSON — the app writes it that way")
    for key, obj in (("_pl_", d.get("plan", {})), ("_td_", d.get("todo", {}))):
        missing = [k for k in obj if key + k not in d["meta"]]
        if missing:
            problems.append(f"{len(missing)} item(s) have no {key} meta timestamp: {', '.join(missing[:3])}")
    out({"cmd": "doctor", "data": path, "remote": remote, "branch": branch,
         "bytes": len(raw), "problems": problems, "ok": not problems})


WRITES = {"hub-set", "hub-move"}


def build_parser():
    ap = argparse.ArgumentParser(description="Cross-system control for the Dopamine Control Center data.")
    ap.add_argument("--data", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="what every system holds + git state").set_defaults(fn=cmd_status)

    p = sub.add_parser("brief", help="one day across every system: plan, to-dos, run, exams")
    p.set_defaults(fn=cmd_brief)
    p.add_argument("--date", default="", help="YYYY-MM-DD, default today")

    sub.add_parser("pull", help="git pull --rebase in p100k-data").set_defaults(fn=cmd_pull)

    p = sub.add_parser("push", help="commit and push data.json"); p.set_defaults(fn=cmd_push)
    p.add_argument("-m", "--message", default="")

    sub.add_parser("hub", help="hub tile order").set_defaults(fn=cmd_hub)

    p = sub.add_parser("hub-set", help="set the whole order"); p.set_defaults(fn=cmd_hub_set)
    p.add_argument("order", help="comma-separated tile ids, e.g. plan,todo,p100k")

    p = sub.add_parser("hub-move", help="move one tile"); p.set_defaults(fn=cmd_hub_move)
    p.add_argument("tile"); p.add_argument("--to", type=int, required=True, help="1-based position")

    sub.add_parser("doctor", help="check clone, branch, sync state, JSON shape").set_defaults(fn=cmd_doctor)

    return ap


def main() -> int:
    a = build_parser().parse_args()
    path = resolve_data_path(a.data)
    d = load(path)
    a.fn(d, a, path)
    if a.cmd in WRITES:
        save(path, d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
