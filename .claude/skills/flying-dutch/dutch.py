#!/usr/bin/env python3
"""Read and write OPERATION FLYING DUTCH — the Dutch inburgering exam system
(p100k-data/data.json).

Four data areas, all optional and all keyed by exam id
(knm, ona, lezen, luisteren, spreken, schrijven):

  oranje[exam] = {date, status, reg}   status: todo|booked|passed|waived
  res[kind][exam] = [{id, title, url, tag, desc}]   kind: study|mock
  ws[exam]  = [{id, what, cat, note, hits, last}]   the weak-spot list
  flash[deck][cardId] = {lvl, right, wrong, seen}   flashcard stats

Meta keys: '_or_<exam>', '_res_<kind>_<exam>', '_ws_<exam>', '_fl_<deck>'.

Subcommands: exams, exam-set, res, res-add, res-edit, res-rm,
             ws, ws-add, ws-edit, ws-hit, ws-reset, ws-rm, flash, flash-reset.
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

EXAMS = {
    "knm": "Dutch Society (KNM)",
    "ona": "Labour Market (ONA)",
    "lezen": "Reading",
    "luisteren": "Listening",
    "spreken": "Speaking",
    "schrijven": "Writing",
}
STATUSES = ("todo", "booked", "passed", "waived")
KINDS = ("study", "mock")


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
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
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
    for k in ("oranje", "res", "ws", "flash", "meta"):
        d.setdefault(k, {})
    return d


def save(path: str, d):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")))


def touch(d, key):
    d["meta"][key] = int(time.time() * 1000)


def gen_id(prefix: str) -> str:
    n, s = int(time.time() * 1000), ""
    a = "0123456789abcdefghijklmnopqrstuvwxyz"
    while n:
        n, r = divmod(n, 36)
        s = a[r] + s
    return prefix + s


def parse_date(s: str) -> str:
    s = (s or "").strip().lower()
    today = date.today()
    if s in ("today", "now"):
        return today.isoformat()
    if s == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        die(f"'{s}' is not a date (use YYYY-MM-DD)")


def exam_id(ref: str) -> str:
    """Exact id, then a name substring: 'reading' -> lezen."""
    q = (ref or "").strip().lower()
    if q in EXAMS:
        return q
    hits = [e for e, n in EXAMS.items() if q and (q in n.lower() or q in e)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        die(f"no exam matches '{ref}' (one of: {', '.join(EXAMS)})", 1)
    die(f"'{ref}' matches {', '.join(hits)}", 1)


def exam_state(d, e):
    st = d["oranje"].get(e) or {}
    return {"date": st.get("date", ""), "status": st.get("status", "todo"),
            "reg": st.get("reg", "")}


def res_list(d, kind, e):
    return d["res"].setdefault(kind, {}).setdefault(e, [])


def ws_list(d, e):
    return d["ws"].setdefault(e, [])


def pick(items, ref, label_key):
    """Find one item by id or by a substring of its label."""
    for it in items:
        if it.get("id") == ref:
            return it
    q = str(ref).strip().lower()
    if q.isdigit() and 1 <= int(q) <= len(items):
        return items[int(q) - 1]
    hits = [it for it in items if q and q in str(it.get(label_key, "")).lower()]
    if not hits:
        die(f"nothing matches '{ref}'", 1)
    if len(hits) > 1:
        die("'%s' matches: %s" % (ref, ", ".join(str(h.get(label_key)) for h in hits)), 1)
    return hits[0]


# ---------------- exams ----------------
def cmd_exams(d, a):
    rows = []
    for e, name in EXAMS.items():
        st = exam_state(d, e)
        away = None
        if st["date"]:
            away = (datetime.strptime(st["date"], "%Y-%m-%d").date() - date.today()).days
        rows.append({"exam": e, "name": name, **st, "days_away": away,
                     "study_resources": len(d["res"].get("study", {}).get(e, [])),
                     "mock_resources": len(d["res"].get("mock", {}).get(e, [])),
                     "weak_spots": len(d["ws"].get(e, []))})
    done = sum(1 for r in rows if r["status"] in ("passed", "waived"))
    out({"cmd": "exams", "done": done, "total": len(rows), "exams": rows})


def cmd_exam_set(d, a):
    e = exam_id(a.exam)
    st = d["oranje"].setdefault(e, {"date": "", "status": "todo"})
    if a.status:
        if a.status not in STATUSES:
            die("--status must be one of " + ", ".join(STATUSES))
        st["status"] = a.status
    if a.date:
        st["date"] = parse_date(a.date)
    if a.clear_date:
        st["date"] = ""
    if a.reg:
        u = a.reg.strip()
        st["reg"] = u if u.startswith("http") else "https://" + u
    if a.reg_default:
        st["reg"] = ""
    touch(d, "_or_" + e)
    out({"cmd": "exam-set", "exam": e, "name": EXAMS[e], **exam_state(d, e)})


# ---------------- resources ----------------
def cmd_res(d, a):
    e = exam_id(a.exam)
    kinds = [a.kind] if a.kind else list(KINDS)
    out({"cmd": "res", "exam": e, "lists": {k: res_list(d, k, e) for k in kinds}})


def cmd_res_add(d, a):
    e = exam_id(a.exam)
    if a.kind not in KINDS:
        die("--kind must be study or mock")
    url = a.url.strip()
    if not a.title.strip() or not url:
        die("--title and --url are required")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    item = {"id": gen_id("r"), "title": a.title.strip(), "url": url,
            "tag": a.tag.strip().lower(), "desc": a.desc.strip()}
    res_list(d, a.kind, e).append(item)
    touch(d, f"_res_{a.kind}_{e}")
    out({"cmd": "res-add", "exam": e, "kind": a.kind, "item": item})


def cmd_res_edit(d, a):
    e = exam_id(a.exam)
    it = pick(res_list(d, a.kind, e), a.ref, "title")
    for f in ("title", "url", "tag", "desc"):
        v = getattr(a, f)
        if v:
            it[f] = v.strip().lower() if f == "tag" else v.strip()
    touch(d, f"_res_{a.kind}_{e}")
    out({"cmd": "res-edit", "exam": e, "kind": a.kind, "item": it})


def cmd_res_rm(d, a):
    e = exam_id(a.exam)
    lst = res_list(d, a.kind, e)
    it = pick(lst, a.ref, "title")
    lst.remove(it)
    touch(d, f"_res_{a.kind}_{e}")
    out({"cmd": "res-rm", "exam": e, "kind": a.kind, "removed": it["title"]})


# ---------------- weak spots ----------------
def ws_sorted(lst):
    """Worst first: most hits, then most recently bitten — same as the app."""
    rows = sorted(lst, key=lambda x: str(x.get("last", "")), reverse=True)
    return sorted(rows, key=lambda x: -(x.get("hits") or 0))


def cmd_ws(d, a):
    e = exam_id(a.exam)
    rows = ws_sorted(ws_list(d, e))
    out({"cmd": "ws", "exam": e, "count": len(rows), "weak_spots": rows})


def cmd_ws_add(d, a):
    e = exam_id(a.exam)
    if not a.what.strip():
        die("--what is required (name the mistake)")
    item = {"id": gen_id("w"), "hits": 1, "last": date.today().isoformat(),
            "what": a.what.strip(), "cat": a.cat.strip().lower(), "note": a.note.strip()}
    ws_list(d, e).append(item)
    touch(d, "_ws_" + e)
    out({"cmd": "ws-add", "exam": e, "item": item})


def cmd_ws_edit(d, a):
    e = exam_id(a.exam)
    it = pick(ws_list(d, e), a.ref, "what")
    for f in ("what", "cat", "note"):
        v = getattr(a, f)
        if v:
            it[f] = v.strip().lower() if f == "cat" else v.strip()
    touch(d, "_ws_" + e)
    out({"cmd": "ws-edit", "exam": e, "item": it})


def cmd_ws_hit(d, a):
    e = exam_id(a.exam)
    it = pick(ws_list(d, e), a.ref, "what")
    it["hits"] = (it.get("hits") or 0) + 1
    it["last"] = date.today().isoformat()
    touch(d, "_ws_" + e)
    out({"cmd": "ws-hit", "exam": e, "item": it})


def cmd_ws_reset(d, a):
    e = exam_id(a.exam)
    it = pick(ws_list(d, e), a.ref, "what")
    it["hits"] = 0
    touch(d, "_ws_" + e)
    out({"cmd": "ws-reset", "exam": e, "item": it})


def cmd_ws_rm(d, a):
    e = exam_id(a.exam)
    lst = ws_list(d, e)
    it = pick(lst, a.ref, "what")
    lst.remove(it)
    touch(d, "_ws_" + e)
    out({"cmd": "ws-rm", "exam": e, "removed": it["what"]})


# ---------------- flashcards ----------------
def cmd_flash(d, a):
    decks = [a.deck] if a.deck else list(d["flash"].keys())
    rows = []
    for dk in decks:
        cards = d["flash"].get(dk) or {}
        seen = [c for c in cards.values() if (c.get("seen") or 0) > 0]
        right = sum(c.get("right", 0) for c in cards.values())
        wrong = sum(c.get("wrong", 0) for c in cards.values())
        worst = sorted(cards.items(), key=lambda kv: -(kv[1].get("wrong") or 0))[:5]
        rows.append({"deck": dk, "cards": len(cards), "seen": len(seen),
                     "right": right, "wrong": wrong,
                     "accuracy": round(right / (right + wrong) * 100) if right + wrong else None,
                     "levels": {str(l): sum(1 for c in cards.values() if (c.get("lvl") or 0) == l)
                                for l in range(0, 6)},
                     "worst_cards": [{"card": k, "wrong": v.get("wrong", 0)} for k, v in worst
                                     if (v.get("wrong") or 0) > 0]})
    out({"cmd": "flash", "decks": rows})


def cmd_flash_reset(d, a):
    dk = a.deck
    cards = d["flash"].get(dk)
    if cards is None:
        die(f"no deck '{dk}' in the data (decks: {', '.join(d['flash']) or 'none yet'})", 1)
    if a.card:
        if a.card not in cards:
            die(f"no card '{a.card}' in deck '{dk}'", 1)
        cards[a.card] = {"lvl": 0, "right": 0, "wrong": 0, "seen": 0}
        n = 1
    else:
        for k in cards:
            cards[k] = {"lvl": 0, "right": 0, "wrong": 0, "seen": 0}
        n = len(cards)
    touch(d, "_fl_" + dk)
    out({"cmd": "flash-reset", "deck": dk, "cards_reset": n})


WRITES = {"exam-set", "res-add", "res-edit", "res-rm", "ws-add", "ws-edit",
          "ws-hit", "ws-reset", "ws-rm", "flash-reset"}


def build_parser():
    ap = argparse.ArgumentParser(description="Read/write OPERATION FLYING DUTCH — the Dutch exam system.")
    ap.add_argument("--data", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("exams", help="all six exams: status, date, counts").set_defaults(fn=cmd_exams)

    p = sub.add_parser("exam-set", help="set an exam's status, date or booking link")
    p.set_defaults(fn=cmd_exam_set)
    p.add_argument("exam"); p.add_argument("--status", default="", choices=[""] + list(STATUSES))
    p.add_argument("--date", default=""); p.add_argument("--clear-date", action="store_true")
    p.add_argument("--reg", default=""); p.add_argument("--reg-default", action="store_true")

    p = sub.add_parser("res", help="list an exam's resources"); p.set_defaults(fn=cmd_res)
    p.add_argument("exam"); p.add_argument("--kind", default="", choices=[""] + list(KINDS))

    p = sub.add_parser("res-add"); p.set_defaults(fn=cmd_res_add)
    p.add_argument("exam"); p.add_argument("--kind", required=True, choices=list(KINDS))
    p.add_argument("--title", required=True); p.add_argument("--url", required=True)
    p.add_argument("--tag", default="", help="official | free | paid")
    p.add_argument("--desc", default="")

    p = sub.add_parser("res-edit"); p.set_defaults(fn=cmd_res_edit)
    p.add_argument("exam"); p.add_argument("ref"); p.add_argument("--kind", required=True, choices=list(KINDS))
    p.add_argument("--title", default=""); p.add_argument("--url", default="")
    p.add_argument("--tag", default=""); p.add_argument("--desc", default="")

    p = sub.add_parser("res-rm"); p.set_defaults(fn=cmd_res_rm)
    p.add_argument("exam"); p.add_argument("ref"); p.add_argument("--kind", required=True, choices=list(KINDS))

    p = sub.add_parser("ws", help="weak spots, worst first"); p.set_defaults(fn=cmd_ws)
    p.add_argument("exam")

    p = sub.add_parser("ws-add"); p.set_defaults(fn=cmd_ws_add)
    p.add_argument("exam"); p.add_argument("--what", required=True)
    p.add_argument("--cat", default=""); p.add_argument("--note", default="")

    p = sub.add_parser("ws-edit"); p.set_defaults(fn=cmd_ws_edit)
    p.add_argument("exam"); p.add_argument("ref")
    p.add_argument("--what", default=""); p.add_argument("--cat", default=""); p.add_argument("--note", default="")

    p = sub.add_parser("ws-hit", help="it bit you again"); p.set_defaults(fn=cmd_ws_hit)
    p.add_argument("exam"); p.add_argument("ref")

    p = sub.add_parser("ws-reset", help="hits back to 0"); p.set_defaults(fn=cmd_ws_reset)
    p.add_argument("exam"); p.add_argument("ref")

    p = sub.add_parser("ws-rm"); p.set_defaults(fn=cmd_ws_rm)
    p.add_argument("exam"); p.add_argument("ref")

    p = sub.add_parser("flash", help="flashcard deck stats"); p.set_defaults(fn=cmd_flash)
    p.add_argument("deck", nargs="?", default="")

    p = sub.add_parser("flash-reset", help="wipe a deck's progress"); p.set_defaults(fn=cmd_flash_reset)
    p.add_argument("deck"); p.add_argument("--card", default="")

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
