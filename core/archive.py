# -*- coding: utf-8 -*-
"""Per-exe archive: structure facts and target history keyed by name + md5."""
from __future__ import annotations

import hashlib
import json
import os
import time

ARCHIVE_DIR = "var/archives"


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _path(exe_md5, name="unknown"):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (name or "unknown"))
    return os.path.join(ARCHIVE_DIR, "%s.json" % safe)


def load(exe_md5, name="unknown"):
    p = _path(exe_md5, name)
    if not os.path.exists(p):
        return {"version": 1, "md5s": [exe_md5], "structure": {},
                "goals": {}, "history": []}
    with open(p, encoding="utf-8") as f:
        arc = json.load(f)
    md5s = arc.setdefault("md5s", [])
    if exe_md5 and exe_md5 not in md5s:
        md5s.append(exe_md5)
        md5s[:] = md5s[-8:]
    return arc


def save(exe_md5, arc, name="unknown"):
    p = _path(exe_md5, name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(arc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def note_structure(exe_md5, recon, name="unknown"):
    arc = load(exe_md5, name)
    arc["structure"] = dict(recon or {})
    save(exe_md5, arc, name)
    return arc["structure"]


def remember(exe_md5, goal, sites, readback=None, name="unknown", note=""):
    arc = load(exe_md5, name)
    key = "%s->%s" % (goal.get("from"), goal.get("to"))
    rec = arc["goals"].get(key) or {"sites": [], "times": 0}
    for s in sites:
        if s not in rec["sites"]:
            rec["sites"].append(s)
    rec["times"] = rec.get("times", 0) + 1
    rec["readback"] = readback
    rec["note"] = note
    rec["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    arc["goals"][key] = rec
    arc["history"].append({"goal": key, "n": len(sites), "at": rec["at"]})
    arc["history"] = arc["history"][-200:]
    save(exe_md5, arc, name)
    return rec


def recall(exe_md5, goal, name="unknown"):
    arc = load(exe_md5, name)
    key = "%s->%s" % (goal.get("from"), goal.get("to"))
    rec = arc["goals"].get(key)
    if not rec:
        return None
    return {"goal": key, "sites": rec.get("sites", []),
            "times": rec.get("times", 0), "readback": rec.get("readback"),
            "at": rec.get("at"), "note": "档案里的记录：我们自己落过盘并回读过"}
