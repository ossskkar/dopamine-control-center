#!/usr/bin/env python3
"""Append a task to the Project 100K todo system (p100k-data/data.json).

The app stores todos under the top-level "todo" object, keyed by project id.
Each project is {id, name, note, ts, tasks[]} and each task is
{id, title, note, due, done, steps[]}. A per-project sync timestamp lives at
meta["_td_<projectId>"]. This script mirrors that shape exactly and rewrites
the file in the app's compact format so the diff is just the new task.

Usage:
  add_todo.py --title "Call the dentist" [--note "..."] \
              [--due 2026-07-25] [--project "Health"]

--project is matched case-insensitively (exact, then substring) against
existing project names. If it is omitted or nothing matches, the task lands in
an "Inbox" project, which is created if it does not already exist.

The data file is located via, in order: $P100K_DATA, a p100k-data sibling of
the dopamine-control-center repo this script ships in, then ~/p100k-data.
On success prints one JSON line describing what was written.
"""
import argparse
import json
import os
import random
import string
import sys
import time

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
    """prefix + base36(ms) + 3 random chars — same shape as the app's ids."""
    rnd = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(3))
    return prefix + _b36(int(time.time() * 1000)) + rnd


def resolve_data_path(explicit: str) -> str:
    if explicit:
        return explicit
    candidates = []
    env = os.environ.get("P100K_DATA")
    if env:
        candidates.append(env)
    # .../<dcc-repo>/.claude/skills/add-todo/add_todo.py -> repo root is 3 up
    repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
    candidates.append(os.path.join(os.path.dirname(repo_root), "p100k-data", "data.json"))
    candidates.append(os.path.expanduser("~/p100k-data/data.json"))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    # fall back to the first non-empty candidate so the error names a real path
    return next((c for c in candidates if c), os.path.expanduser("~/p100k-data/data.json"))


def find_project(todo: dict, name: str):
    if not name:
        return None
    q = name.strip().lower()
    for pid, p in todo.items():
        if p.get("name", "").strip().lower() == q:
            return pid
    for pid, p in todo.items():
        pn = p.get("name", "").strip().lower()
        if pn and (q in pn or pn in q):
            return pid
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Add a task to the Project 100K todo system.")
    ap.add_argument("--title", required=True, help="Task title (what to do).")
    ap.add_argument("--note", default="", help="Optional longer note / detail.")
    ap.add_argument("--due", default="", help="Optional due date, YYYY-MM-DD.")
    ap.add_argument("--project", default="", help="Target project name; falls back to Inbox.")
    ap.add_argument("--data", default="", help="Explicit path to data.json.")
    a = ap.parse_args()

    if not a.title.strip():
        print("error: --title is empty", file=sys.stderr)
        return 2
    if a.due:
        try:
            time.strptime(a.due, "%Y-%m-%d")
        except ValueError:
            print(f"error: --due '{a.due}' is not YYYY-MM-DD", file=sys.stderr)
            return 2

    path = resolve_data_path(a.data)
    if not os.path.exists(path):
        print(f"error: data.json not found at {path}", file=sys.stderr)
        return 1

    with open(path, encoding="utf-8") as f:
        d = json.load(f)

    todo = d.setdefault("todo", {})
    meta = d.setdefault("meta", {})

    pid = find_project(todo, a.project)
    created_project = False
    if pid is None:
        pid = find_project(todo, "Inbox")
        if pid is None:
            pid = gen_id("p")
            todo[pid] = {
                "id": pid,
                "name": "Inbox",
                "note": "Captured in conversation; triage later.",
                "ts": int(time.time() * 1000),
                "tasks": [],
            }
            created_project = True

    task = {
        "id": gen_id("t"),
        "title": a.title.strip(),
        "note": a.note.strip(),
        "due": a.due.strip(),
        "done": False,
        "steps": [],
    }
    todo[pid].setdefault("tasks", []).append(task)
    meta["_td_" + pid] = int(time.time() * 1000)

    # Rewrite in the app's exact on-disk format: compact, UTF-8, no trailing NL.
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))

    print(json.dumps({
        "project": todo[pid]["name"],
        "project_id": pid,
        "created_project": created_project,
        "task": task,
        "data": path,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
