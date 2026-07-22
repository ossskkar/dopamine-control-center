#!/usr/bin/env python3
"""Read-only query tool for the Project 100K data (p100k-data/data.json).

Answers questions about the "Mission: Eventually" board — projects, tasks and
steps — and can also inspect any other part of the data file. It NEVER writes:
no mutation, no commit, safe to run any time. Every subcommand prints JSON;
the caller turns it into plain language.

Subcommands:
    dump    [--status open|done|all]   Full board (default: all).
    find    TEXT                       Search projects/tasks/steps for TEXT.
    due     [--on D] [--before D]      Tasks/steps with due dates (optionally
                                       exactly on D, or on/before D). YYYY-MM-DD.
    overdue                            Undone items due before today.
    today                              Undone items due today.
    summary                            Counts and completion per project + totals.
    raw     [DOTPATH]                  Inspect any key path in data.json,
                                       e.g. `raw settings.raceDate`, `raw days`,
                                       `raw` (top-level keys). Read-only.
"""
import argparse
import json
import os
import sys
from datetime import date


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


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def load(path: str):
    if not os.path.exists(path):
        print(f"error: data.json not found at {path}", file=sys.stderr)
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("todo", {})
    return d


def iter_tasks(todo):
    for pid, p in todo.items():
        for t in p.get("tasks", []):
            yield p, t


def task_view(p, t, with_steps=False):
    steps = t.get("steps", [])
    v = {
        "id": t["id"], "title": t.get("title", ""), "project": p.get("name", ""),
        "due": t.get("due", ""), "done": t.get("done", False),
        "steps_done": sum(1 for s in steps if s.get("done")), "steps_total": len(steps),
    }
    if with_steps:
        v["steps"] = [{"title": s.get("title", ""), "done": s.get("done", False),
                       "due": s.get("due", "")} for s in steps]
    return v


def cmd_dump(d, a):
    projects = []
    for pid, p in d["todo"].items():
        tasks = [task_view(p, t, with_steps=True) for t in p.get("tasks", [])
                 if a.status == "all"
                 or (a.status == "done" and t.get("done"))
                 or (a.status == "open" and not t.get("done"))]
        projects.append({"id": pid, "name": p.get("name", ""), "note": p.get("note", ""),
                         "tasks": tasks})
    out({"query": "dump", "status": a.status, "projects": projects})


def cmd_find(d, a):
    q = a.text.strip().lower()
    hits = []
    for p, t in iter_tasks(d["todo"]):
        if q in t.get("title", "").lower() or q in t.get("note", "").lower():
            hits.append({"kind": "task", **task_view(p, t)})
        for s in t.get("steps", []):
            if q in s.get("title", "").lower():
                hits.append({"kind": "step", "title": s.get("title", ""),
                             "done": s.get("done", False), "task": t.get("title", ""),
                             "project": p.get("name", "")})
    for pid, p in d["todo"].items():
        if q in p.get("name", "").lower() or q in p.get("note", "").lower():
            hits.append({"kind": "project", "name": p.get("name", ""), "id": pid})
    out({"query": "find", "text": a.text, "count": len(hits), "hits": hits})


def _dued(d, pred):
    rows = []
    for p, t in iter_tasks(d["todo"]):
        due = t.get("due", "")
        if due and pred(due):
            rows.append(task_view(p, t))
    return rows


def cmd_due(d, a):
    if a.on:
        rows = _dued(d, lambda due: due == a.on)
    elif a.before:
        rows = _dued(d, lambda due: due <= a.before)
    else:
        rows = _dued(d, lambda due: True)
    out({"query": "due", "on": a.on, "before": a.before, "count": len(rows), "tasks": rows})


def cmd_overdue(d, a):
    today = date.today().isoformat()
    rows = [task_view(p, t) for p, t in iter_tasks(d["todo"])
            if t.get("due") and t["due"] < today and not t.get("done")]
    out({"query": "overdue", "today": today, "count": len(rows), "tasks": rows})


def cmd_today(d, a):
    today = date.today().isoformat()
    rows = [task_view(p, t) for p, t in iter_tasks(d["todo"])
            if t.get("due") == today and not t.get("done")]
    out({"query": "today", "today": today, "count": len(rows), "tasks": rows})


def cmd_summary(d, a):
    rows, tot_t, tot_done, tot_s, tot_s_done = [], 0, 0, 0, 0
    for pid, p in d["todo"].items():
        tasks = p.get("tasks", [])
        done = sum(1 for t in tasks if t.get("done"))
        steps = [s for t in tasks for s in t.get("steps", [])]
        sdone = sum(1 for s in steps if s.get("done"))
        rows.append({"project": p.get("name", ""), "tasks": len(tasks), "tasks_done": done,
                     "steps": len(steps), "steps_done": sdone})
        tot_t += len(tasks); tot_done += done; tot_s += len(steps); tot_s_done += sdone
    out({"query": "summary", "projects": rows,
         "totals": {"projects": len(rows), "tasks": tot_t, "tasks_done": tot_done,
                    "steps": tot_s, "steps_done": tot_s_done}})


def cmd_raw(d, a):
    node = d
    trail = []
    if a.path:
        for part in a.path.split("."):
            trail.append(part)
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                print(f"error: no key path '{'.'.join(trail)}'", file=sys.stderr)
                raise SystemExit(1)
    if isinstance(node, dict):
        out({"query": "raw", "path": a.path or "", "keys": list(node.keys()), "value": node})
    else:
        out({"query": "raw", "path": a.path or "", "value": node})


def build_parser():
    ap = argparse.ArgumentParser(description="Read-only queries over the Project 100K data.")
    ap.add_argument("--data", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dump"); p.set_defaults(fn=cmd_dump)
    p.add_argument("--status", choices=["open", "done", "all"], default="all")

    p = sub.add_parser("find"); p.set_defaults(fn=cmd_find); p.add_argument("text")

    p = sub.add_parser("due"); p.set_defaults(fn=cmd_due)
    p.add_argument("--on", default=""); p.add_argument("--before", default="")

    sub.add_parser("overdue").set_defaults(fn=cmd_overdue)
    sub.add_parser("today").set_defaults(fn=cmd_today)
    sub.add_parser("summary").set_defaults(fn=cmd_summary)

    p = sub.add_parser("raw"); p.set_defaults(fn=cmd_raw)
    p.add_argument("path", nargs="?", default="")

    return ap


def main() -> int:
    a = build_parser().parse_args()
    d = load(resolve_data_path(a.data))
    a.fn(d, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
