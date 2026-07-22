#!/usr/bin/env python3
"""Full-control CLI for the "Mission: Eventually" board (p100k-data/data.json).

"Mission: Eventually" is the app's display name for the to-do board — the
top-level "todo" object. This tool gives full control over that board's
projects, tasks and steps. It is a SEPARATE skill from add-todo (which only
quick-captures a single task); both act on the same real board because that is
the one system the app renders.

Data model (observed from the live data — do not reshape it):

    todo[<pid "p…">] = {
        "id": pid, "name": str, "note": str, "ts": <ms>,
        "tasks": [
            {"id": <tid "t…">, "title": str, "note": str,
             "due": "" | "YYYY-MM-DD", "done": bool,
             "steps": [ {"id": <sid "s…">, "title": str, "done": bool, "due": ""}, ... ]},
            ...
        ],
    }
    meta["_td_<pid>"] = <ms>   # per-project sync timestamp

The file is rewritten in the app's exact compact, UTF-8, newline-free format.
Every subcommand prints one JSON result line. This tool never reshapes tasks
or projects beyond the fields above and never touches non-todo data.

Project subcommands:
    projects
    project-add    --name NAME [--note NOTE]
    project-edit   PREF [--name NAME] [--note NOTE]
    project-move   PREF --to POS            (1-based position)
    project-rm     PREF                     (deletes its tasks too)

Task subcommands (TREF matches by task id or title substring, any project):
    tasks          [PREF]
    task-add       PREF --title T [--note N] [--due D]
    task-edit      TREF [--title T] [--note N] [--due D]
    task-done      TREF
    task-undone    TREF
    task-move      TREF [--to PREF] [--pos N]   (change project and/or reorder)
    task-rm        TREF

Step subcommands (SREF is a 1-based index or a step id, within that task):
    step-add       TREF --text TEXT
    step-edit      TREF SREF [--title T] [--due D]
    step-move      TREF SREF --to N             (reorder within the task)
    step-done      TREF SREF
    step-undone    TREF SREF
    step-rm        TREF SREF

PREF/TREF resolve by exact id first, else case-insensitive name/title
substring; an ambiguous match errors with the candidate list instead of
guessing.
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
    rnd = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(3))
    return prefix + _b36(int(time.time() * 1000)) + rnd


def now_ms() -> int:
    return int(time.time() * 1000)


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


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


def load(path: str):
    if not os.path.exists(path):
        die(f"data.json not found at {path}")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("todo", {})
    d.setdefault("meta", {})
    return d


def save(path: str, d: dict):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


def touch(d: dict, pid: str):
    d["meta"]["_td_" + pid] = now_ms()


def valid_due(due: str):
    if due == "":
        return
    try:
        time.strptime(due, "%Y-%m-%d")
    except ValueError:
        die(f"--due '{due}' is not YYYY-MM-DD", 2)


def out(obj):
    print(json.dumps(obj, ensure_ascii=False))


def resolve_project(todo: dict, ref: str) -> str:
    if ref in todo:
        return ref
    q = ref.strip().lower()
    hits = [pid for pid, p in todo.items() if q and q in p.get("name", "").strip().lower()]
    if not hits:
        die(f"no project matches '{ref}'")
    if len(hits) > 1:
        names = "; ".join(f"{pid}={todo[pid]['name']!r}" for pid in hits)
        die(f"project '{ref}' is ambiguous — matches: {names}. Use an id.")
    return hits[0]


def resolve_task(todo: dict, ref: str):
    """Return (pid, task_index) for a task matched across all projects."""
    q = ref.strip().lower()
    hits = []
    for pid, p in todo.items():
        for i, t in enumerate(p.get("tasks", [])):
            if t.get("id") == ref:
                return pid, i
            if q and q in t.get("title", "").strip().lower():
                hits.append((pid, i, t.get("title", "")))
    if not hits:
        die(f"no task matches '{ref}'")
    if len(hits) > 1:
        names = "; ".join(f"{todo[pid]['tasks'][i]['id']}={title!r} (in {todo[pid]['name']})"
                          for pid, i, title in hits)
        die(f"task '{ref}' is ambiguous — matches: {names}. Use an id.")
    pid, i, _ = hits[0]
    return pid, i


def resolve_step(task: dict, ref: str) -> int:
    steps = task.get("steps", [])
    for i, s in enumerate(steps):
        if s.get("id") == ref:
            return i
    if ref.isdigit():
        idx = int(ref) - 1
        if 0 <= idx < len(steps):
            return idx
    die(f"no step '{ref}' in task {task['id']}")


# ---- projects ------------------------------------------------------------

def cmd_projects(d, path, a):
    rows = []
    for pid, p in d["todo"].items():
        tasks = p.get("tasks", [])
        rows.append({
            "id": pid, "name": p.get("name", ""), "note": p.get("note", ""),
            "tasks_done": sum(1 for t in tasks if t.get("done")),
            "tasks_total": len(tasks),
        })
    out({"action": "projects", "count": len(rows), "projects": rows})


def cmd_project_add(d, path, a):
    if not a.name.strip():
        die("--name is empty", 2)
    pid = gen_id("p")
    d["todo"][pid] = {"id": pid, "name": a.name.strip(), "note": (a.note or "").strip(),
                      "ts": now_ms(), "tasks": []}
    touch(d, pid)
    save(path, d)
    out({"action": "project-add", "project": d["todo"][pid]})


def cmd_project_edit(d, path, a):
    pid = resolve_project(d["todo"], a.ref)
    p = d["todo"][pid]
    if a.name is not None:
        if not a.name.strip():
            die("--name is empty", 2)
        p["name"] = a.name.strip()
    if a.note is not None:
        p["note"] = a.note.strip()
    touch(d, pid)
    save(path, d)
    out({"action": "project-edit", "project": p})


def cmd_project_move(d, path, a):
    pid = resolve_project(d["todo"], a.ref)
    ids = [k for k in d["todo"].keys() if k != pid]
    pos = max(1, min(a.to, len(ids) + 1)) - 1
    ids.insert(pos, pid)
    d["todo"] = {k: d["todo"][k] for k in ids}
    touch(d, pid)
    save(path, d)
    out({"action": "project-move", "order": [{"id": k, "name": d["todo"][k]["name"]} for k in ids]})


def cmd_project_rm(d, path, a):
    pid = resolve_project(d["todo"], a.ref)
    removed = d["todo"].pop(pid)
    d["meta"].pop("_td_" + pid, None)
    save(path, d)
    out({"action": "project-rm", "removed_project": removed["name"],
         "removed_tasks": len(removed.get("tasks", []))})


# ---- tasks ---------------------------------------------------------------

def cmd_tasks(d, path, a):
    pids = [resolve_project(d["todo"], a.ref)] if a.ref else list(d["todo"].keys())
    rows = []
    for pid in pids:
        p = d["todo"][pid]
        for t in p.get("tasks", []):
            steps = t.get("steps", [])
            rows.append({
                "id": t["id"], "title": t.get("title", ""), "project": p.get("name", ""),
                "due": t.get("due", ""), "done": t.get("done", False),
                "steps_done": sum(1 for s in steps if s.get("done")), "steps_total": len(steps),
            })
    out({"action": "tasks", "count": len(rows), "tasks": rows})


def cmd_task_add(d, path, a):
    pid = resolve_project(d["todo"], a.ref)
    if not a.title.strip():
        die("--title is empty", 2)
    valid_due(a.due)
    task = {"id": gen_id("t"), "title": a.title.strip(), "note": (a.note or "").strip(),
            "due": a.due.strip(), "done": False, "steps": []}
    d["todo"][pid].setdefault("tasks", []).append(task)
    touch(d, pid)
    save(path, d)
    out({"action": "task-add", "project": d["todo"][pid]["name"], "task": task})


def cmd_task_edit(d, path, a):
    pid, i = resolve_task(d["todo"], a.ref)
    t = d["todo"][pid]["tasks"][i]
    if a.title is not None:
        if not a.title.strip():
            die("--title is empty", 2)
        t["title"] = a.title.strip()
    if a.note is not None:
        t["note"] = a.note.strip()
    if a.due is not None:
        valid_due(a.due)
        t["due"] = a.due.strip()
    touch(d, pid)
    save(path, d)
    out({"action": "task-edit", "task": t})


def _set_done(d, path, ref, value):
    pid, i = resolve_task(d["todo"], ref)
    d["todo"][pid]["tasks"][i]["done"] = value
    touch(d, pid)
    save(path, d)
    out({"action": "task-done" if value else "task-undone", "task": d["todo"][pid]["tasks"][i]})


def cmd_task_done(d, path, a):
    _set_done(d, path, a.ref, True)


def cmd_task_undone(d, path, a):
    _set_done(d, path, a.ref, False)


def cmd_task_move(d, path, a):
    if a.to is None and a.pos is None:
        die("task-move needs --to <project> and/or --pos <n>", 2)
    pid, i = resolve_task(d["todo"], a.ref)
    dest = resolve_project(d["todo"], a.to) if a.to else pid
    task = d["todo"][pid]["tasks"].pop(i)
    tasks = d["todo"][dest].setdefault("tasks", [])
    pos = (max(1, min(a.pos, len(tasks) + 1)) - 1) if a.pos is not None else len(tasks)
    tasks.insert(pos, task)
    touch(d, pid)
    if dest != pid:
        touch(d, dest)
    save(path, d)
    out({"action": "task-move", "task": task["title"],
         "from": d["todo"][pid]["name"], "to": d["todo"][dest]["name"], "pos": pos + 1})


def cmd_task_rm(d, path, a):
    pid, i = resolve_task(d["todo"], a.ref)
    removed = d["todo"][pid]["tasks"].pop(i)
    touch(d, pid)
    save(path, d)
    out({"action": "task-rm", "removed": removed["title"], "project": d["todo"][pid]["name"]})


# ---- steps ---------------------------------------------------------------

def cmd_step_add(d, path, a):
    pid, i = resolve_task(d["todo"], a.ref)
    t = d["todo"][pid]["tasks"][i]
    if not a.text.strip():
        die("--text is empty", 2)
    step = {"id": gen_id("s"), "title": a.text.strip(), "done": False, "due": ""}
    t.setdefault("steps", []).append(step)
    touch(d, pid)
    save(path, d)
    out({"action": "step-add", "task": t["title"], "step": step})


def _step_done(d, path, ref, sref, value):
    pid, i = resolve_task(d["todo"], ref)
    t = d["todo"][pid]["tasks"][i]
    si = resolve_step(t, sref)
    t["steps"][si]["done"] = value
    touch(d, pid)
    save(path, d)
    out({"action": "step-done" if value else "step-undone", "task": t["title"], "step": t["steps"][si]})


def cmd_step_done(d, path, a):
    _step_done(d, path, a.ref, a.step, True)


def cmd_step_undone(d, path, a):
    _step_done(d, path, a.ref, a.step, False)


def cmd_step_rm(d, path, a):
    pid, i = resolve_task(d["todo"], a.ref)
    t = d["todo"][pid]["tasks"][i]
    si = resolve_step(t, a.step)
    removed = t["steps"].pop(si)
    touch(d, pid)
    save(path, d)
    out({"action": "step-rm", "task": t["title"], "removed": removed.get("title", "")})


def cmd_step_edit(d, path, a):
    pid, i = resolve_task(d["todo"], a.ref)
    t = d["todo"][pid]["tasks"][i]
    si = resolve_step(t, a.step)
    s = t["steps"][si]
    if a.title is not None:
        if not a.title.strip():
            die("--title is empty", 2)
        s["title"] = a.title.strip()
    if a.due is not None:
        valid_due(a.due)
        s["due"] = a.due.strip()
    touch(d, pid)
    save(path, d)
    out({"action": "step-edit", "task": t["title"], "step": s})


def cmd_step_move(d, path, a):
    pid, i = resolve_task(d["todo"], a.ref)
    t = d["todo"][pid]["tasks"][i]
    si = resolve_step(t, a.step)
    step = t["steps"].pop(si)
    pos = max(1, min(a.to, len(t["steps"]) + 1)) - 1
    t["steps"].insert(pos, step)
    touch(d, pid)
    save(path, d)
    out({"action": "step-move", "task": t["title"],
         "order": [s.get("title", "") for s in t["steps"]]})


def build_parser():
    ap = argparse.ArgumentParser(description="Full control over the Mission: Eventually board.")
    ap.add_argument("--data", default="", help="Explicit path to data.json.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("projects").set_defaults(fn=cmd_projects)

    p = sub.add_parser("project-add"); p.set_defaults(fn=cmd_project_add)
    p.add_argument("--name", required=True); p.add_argument("--note", default="")

    p = sub.add_parser("project-edit"); p.set_defaults(fn=cmd_project_edit)
    p.add_argument("ref"); p.add_argument("--name", default=None); p.add_argument("--note", default=None)

    p = sub.add_parser("project-move"); p.set_defaults(fn=cmd_project_move)
    p.add_argument("ref"); p.add_argument("--to", type=int, required=True)

    p = sub.add_parser("project-rm"); p.set_defaults(fn=cmd_project_rm)
    p.add_argument("ref")

    p = sub.add_parser("tasks"); p.set_defaults(fn=cmd_tasks)
    p.add_argument("ref", nargs="?", default="")

    p = sub.add_parser("task-add"); p.set_defaults(fn=cmd_task_add)
    p.add_argument("ref"); p.add_argument("--title", required=True)
    p.add_argument("--note", default=""); p.add_argument("--due", default="")

    p = sub.add_parser("task-edit"); p.set_defaults(fn=cmd_task_edit)
    p.add_argument("ref"); p.add_argument("--title", default=None)
    p.add_argument("--note", default=None); p.add_argument("--due", default=None)

    p = sub.add_parser("task-done"); p.set_defaults(fn=cmd_task_done); p.add_argument("ref")
    p = sub.add_parser("task-undone"); p.set_defaults(fn=cmd_task_undone); p.add_argument("ref")

    p = sub.add_parser("task-move"); p.set_defaults(fn=cmd_task_move)
    p.add_argument("ref"); p.add_argument("--to", default=None); p.add_argument("--pos", type=int, default=None)

    p = sub.add_parser("task-rm"); p.set_defaults(fn=cmd_task_rm); p.add_argument("ref")

    p = sub.add_parser("step-add"); p.set_defaults(fn=cmd_step_add)
    p.add_argument("ref"); p.add_argument("--text", required=True)

    p = sub.add_parser("step-edit"); p.set_defaults(fn=cmd_step_edit)
    p.add_argument("ref"); p.add_argument("step")
    p.add_argument("--title", default=None); p.add_argument("--due", default=None)

    p = sub.add_parser("step-move"); p.set_defaults(fn=cmd_step_move)
    p.add_argument("ref"); p.add_argument("step"); p.add_argument("--to", type=int, required=True)

    p = sub.add_parser("step-done"); p.set_defaults(fn=cmd_step_done)
    p.add_argument("ref"); p.add_argument("step")
    p = sub.add_parser("step-undone"); p.set_defaults(fn=cmd_step_undone)
    p.add_argument("ref"); p.add_argument("step")
    p = sub.add_parser("step-rm"); p.set_defaults(fn=cmd_step_rm)
    p.add_argument("ref"); p.add_argument("step")

    return ap


def main() -> int:
    a = build_parser().parse_args()
    path = resolve_data_path(a.data)
    d = load(path)
    a.fn(d, path, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
