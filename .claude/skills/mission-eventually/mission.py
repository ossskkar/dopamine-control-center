#!/usr/bin/env python3
"""Full-control CLI for the "Mission Eventually" system (p100k-data/data.json).

Mission Eventually is a separate long-term / someday board — NOT the todo list.
Missions live under the top-level "mission" object, keyed by mission id:

    mission[<mid>] = {
        "id":    <mid>,
        "title": str,
        "note":  str,
        "due":   "" | "YYYY-MM-DD",
        "status": "someday" | "active" | "done",
        "steps": [ {"id": <sid>, "text": str, "done": bool}, ... ],
        "ts":    <created ms>,
    }

Each mission has a sync timestamp at meta["_mi_<mid>"], mirroring the app's
per-item "_td_" convention for todos. The file is rewritten in the app's exact
compact, UTF-8, newline-free format so diffs stay minimal.

Subcommands (every one prints a JSON result line):
    add     --title T [--note N] [--due D] [--status S]
    list    [--status S]
    get     REF
    update  REF [--title T] [--note N] [--due D] [--status S]
    status  REF STATE              (STATE = someday|active|done)
    step    REF add TEXT
    step    REF done  STEP
    step    REF undone STEP
    step    REF rm    STEP
    rm      REF

REF resolves a mission by exact id, else by case-insensitive title substring.
An ambiguous title match errors with the candidate list instead of guessing.
STEP is a 1-based index or a step id. This tool never touches the todo data.
"""
import argparse
import json
import os
import random
import string
import sys
import time

STATUSES = ("someday", "active", "done")
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def _b36(n: int) -> str:
    if n == 0:
        return "0"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _ALPHABET[r] + out
    return out


def gen_id(prefix: str) -> str:
    rnd = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(3))
    return prefix + _b36(int(time.time() * 1000)) + rnd


def now_ms() -> int:
    return int(time.time() * 1000)


def resolve_data_path(explicit: str) -> str:
    if explicit:
        return explicit
    candidates = []
    env = os.environ.get("P100K_DATA")
    if env:
        candidates.append(env)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    candidates.append(os.path.join(os.path.dirname(repo_root), "p100k-data", "data.json"))
    candidates.append(os.path.expanduser("~/p100k-data/data.json"))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return next((c for c in candidates if c), os.path.expanduser("~/p100k-data/data.json"))


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load(path: str):
    if not os.path.exists(path):
        die(f"data.json not found at {path}")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("mission", {})
    d.setdefault("meta", {})
    return d


def save(path: str, d: dict):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


def valid_due(due: str):
    if due == "":
        return
    try:
        time.strptime(due, "%Y-%m-%d")
    except ValueError:
        die(f"--due '{due}' is not YYYY-MM-DD", 2)


def resolve(mission: dict, ref: str) -> str:
    if ref in mission:
        return ref
    q = ref.strip().lower()
    hits = [mid for mid, m in mission.items() if q and q in m.get("title", "").strip().lower()]
    if not hits:
        die(f"no mission matches '{ref}'")
    if len(hits) > 1:
        names = "; ".join(f"{mid}={mission[mid]['title']!r}" for mid in hits)
        die(f"'{ref}' is ambiguous — matches: {names}. Use an id.")
    return hits[0]


def touch(d: dict, mid: str):
    d["meta"]["_mi_" + mid] = now_ms()


def find_step(m: dict, ref: str) -> int:
    steps = m.get("steps", [])
    for i, s in enumerate(steps):
        if s.get("id") == ref:
            return i
    if ref.isdigit():
        idx = int(ref) - 1
        if 0 <= idx < len(steps):
            return idx
    die(f"no step '{ref}' in mission {m['id']}")


def out(obj):
    print(json.dumps(obj, ensure_ascii=False))


# ---- subcommand handlers -------------------------------------------------

def cmd_add(d, path, a):
    if not a.title.strip():
        die("--title is empty", 2)
    valid_due(a.due)
    status = a.status or "someday"
    if status not in STATUSES:
        die(f"--status must be one of {STATUSES}", 2)
    mid = gen_id("m")
    m = {
        "id": mid,
        "title": a.title.strip(),
        "note": (a.note or "").strip(),
        "due": a.due.strip(),
        "status": status,
        "steps": [],
        "ts": now_ms(),
    }
    d["mission"][mid] = m
    touch(d, mid)
    save(path, d)
    out({"action": "add", "mission": m})


def cmd_list(d, path, a):
    rows = []
    for mid, m in d["mission"].items():
        if a.status and m.get("status") != a.status:
            continue
        steps = m.get("steps", [])
        rows.append({
            "id": mid,
            "title": m.get("title", ""),
            "status": m.get("status", ""),
            "due": m.get("due", ""),
            "steps_done": sum(1 for s in steps if s.get("done")),
            "steps_total": len(steps),
        })
    out({"action": "list", "count": len(rows), "missions": rows})


def cmd_get(d, path, a):
    mid = resolve(d["mission"], a.ref)
    out({"action": "get", "mission": d["mission"][mid]})


def cmd_update(d, path, a):
    mid = resolve(d["mission"], a.ref)
    m = d["mission"][mid]
    if a.title is not None:
        if not a.title.strip():
            die("--title is empty", 2)
        m["title"] = a.title.strip()
    if a.note is not None:
        m["note"] = a.note.strip()
    if a.due is not None:
        valid_due(a.due)
        m["due"] = a.due.strip()
    if a.status is not None:
        if a.status not in STATUSES:
            die(f"--status must be one of {STATUSES}", 2)
        m["status"] = a.status
    touch(d, mid)
    save(path, d)
    out({"action": "update", "mission": m})


def cmd_status(d, path, a):
    if a.state not in STATUSES:
        die(f"status must be one of {STATUSES}", 2)
    mid = resolve(d["mission"], a.ref)
    d["mission"][mid]["status"] = a.state
    touch(d, mid)
    save(path, d)
    out({"action": "status", "mission": d["mission"][mid]})


def cmd_step(d, path, a):
    mid = resolve(d["mission"], a.ref)
    m = d["mission"][mid]
    m.setdefault("steps", [])
    if a.op == "add":
        text = " ".join(a.args).strip()
        if not text:
            die("step add needs text", 2)
        step = {"id": gen_id("s"), "text": text, "done": False}
        m["steps"].append(step)
        result = step
    elif a.op in ("done", "undone"):
        if not a.args:
            die(f"step {a.op} needs a step index or id", 2)
        i = find_step(m, a.args[0])
        m["steps"][i]["done"] = (a.op == "done")
        result = m["steps"][i]
    elif a.op == "rm":
        if not a.args:
            die("step rm needs a step index or id", 2)
        i = find_step(m, a.args[0])
        result = m["steps"].pop(i)
    else:
        die(f"unknown step op '{a.op}'", 2)
    touch(d, mid)
    save(path, d)
    out({"action": "step", "op": a.op, "mission_id": mid, "step": result})


def cmd_rm(d, path, a):
    mid = resolve(d["mission"], a.ref)
    removed = d["mission"].pop(mid)
    d["meta"].pop("_mi_" + mid, None)
    save(path, d)
    out({"action": "rm", "removed": removed})


def build_parser():
    ap = argparse.ArgumentParser(description="Full control over the Mission Eventually system.")
    ap.add_argument("--data", default="", help="Explicit path to data.json.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add"); p.set_defaults(fn=cmd_add)
    p.add_argument("--title", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--due", default="")
    p.add_argument("--status", default="")

    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    p.add_argument("--status", default="")

    p = sub.add_parser("get"); p.set_defaults(fn=cmd_get)
    p.add_argument("ref")

    p = sub.add_parser("update"); p.set_defaults(fn=cmd_update)
    p.add_argument("ref")
    p.add_argument("--title", default=None)
    p.add_argument("--note", default=None)
    p.add_argument("--due", default=None)
    p.add_argument("--status", default=None)

    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    p.add_argument("ref")
    p.add_argument("state")

    p = sub.add_parser("step"); p.set_defaults(fn=cmd_step)
    p.add_argument("ref")
    p.add_argument("op", choices=["add", "done", "undone", "rm"])
    p.add_argument("args", nargs="*")

    p = sub.add_parser("rm"); p.set_defaults(fn=cmd_rm)
    p.add_argument("ref")

    return ap


def main() -> int:
    a = build_parser().parse_args()
    path = resolve_data_path(a.data)
    d = load(path)
    a.fn(d, path, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
