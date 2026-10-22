# -*- coding: utf-8 -*-
"""Self-registration for organs, gates and policies."""
from __future__ import annotations

ORGANS = {}      # name -> {"fn": callable, "gates": set, "desc": str}
GATES = {}       # name -> {"fn": callable, "rank": int, "desc": str}
POLICIES = []    # [(rank, name, fn)]


def organ(name, gates, desc="", **extra):
    def deco(fn):
        spec = {"fn": fn, "gates": set(gates), "desc": desc, "name": name}
        spec.update(extra)
        ORGANS[name] = spec
        return fn
    return deco


def gate(name, rank=0, desc="", **extra):
    def deco(fn):
        spec = {"fn": fn, "rank": rank, "desc": desc, "name": name}
        spec.update(extra)
        GATES[name] = spec
        return fn
    return deco


def policy(rank=0, desc=""):
    def deco(fn):
        POLICIES.append((rank, fn.__name__, fn))
        POLICIES.sort(key=lambda x: -x[0])
        fn.desc = desc
        return fn
    return deco


def organs_for(gate_name):
    return [o for o in ORGANS.values() if gate_name in o["gates"]]


def names():
    return {"organs": list(ORGANS), "gates": list(GATES),
            "policies": [p[1] for p in POLICIES]}


def describe():
    rows = ["器官（填证据）："]
    for o in ORGANS.values():
        rows.append("  %-8s 回答 %-22s %s" % (o["name"], "/".join(sorted(o["gates"])), o["desc"]))
    rows.append("硬门（不许凑数）：")
    for g in GATES.values():
        rows.append("  %-8s rank=%d  %s" % (g["name"], g["rank"], g["desc"]))
    rows.append("类别判定（谁赢）：")
    for _r, n, fn in POLICIES:
        rows.append("  %-8s %s" % (n, getattr(fn, "desc", "")))
    return "\n".join(rows)

WINDOWLESS = ("record", "typed")


def lead_of(gate):
    prefer = {"record": "record", "arm": "reg", "typed": "typed"}
    if gate in prefer:
        return prefer[gate]
    for name, spec in ORGANS.items():
        if gate in (spec.get("gates") or []):
            return name
    return "data"
