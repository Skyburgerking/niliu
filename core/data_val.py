# -*- coding: utf-8 -*-
"""Organ: bare globals in .data/.rdata that are referenced by absolute address."""
from __future__ import annotations

import addr as AD
import registry as R

_SECS = (".data", ".rdata")


def _refs(m):
    got = m.get("_dataval_refs")
    if got is not None:
        return got
    refs = {}
    for c in m["consts"]:
        a = c["imm"]
        if 0x401000 <= a < 0x75DC1C:
            refs.setdefault(a, []).append(c)
    m["_dataval_refs"] = refs
    return refs


@R.organ("dataval", ["dataval"], "裸变量：值在数据段、且地址被代码引用过")
def organ_dataval(m, value, goal=None):
    goal = goal or {}
    w = int(goal.get("width") or 4)
    if w not in (1, 2, 4, 8) or value is None:
        return []
    raw = bytes(m["_raw"])
    refs = _refs(m)
    base = m["base"]
    pat = (int(value) & ((1 << (w * 8)) - 1)).to_bytes(w, "little")
    out = []
    for name in _SECS:
        sec = m["sections"].get(name)
        if not sec:
            continue
        lo = sec["roff"]
        hi = min(sec["roff"] + sec["rsize"], len(raw) - w)
        step = 4 if w <= 4 else 8
        for o in range(lo - lo % step, hi, step):
            if raw[o:o + w] != pat:
                continue
            hits = refs.get(base + o) or []
            if not hits:
                continue
            out.append({"va": base + o, "fo": o, "fo_imm": o, "imm": value,
                        "mn": "data", "w": w,
                        "text": ".data[%#x] = %d（被引用 %d 次）" % (o, value, len(hits)),
                        "_base": "abs", "_disp": 0, "_nref": len(hits),
                        "_refva": [hex(h["va"]) for h in hits[:4]]})
    return out


@R.gate("dataval", rank=1, desc="裸变量门：数据段里的值 + 地址被代码引用 + 独立回读")
def gate_dataval(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    fo = c.get("fo_imm")
    w = int(c.get("w") or 4)
    if fo is None or fo < 0 or fo + w > len(raw):
        return None
    got = int.from_bytes(raw[fo:fo + w], "little")
    if got != (int(goal.get("from") or 0) & ((1 << (w * 8)) - 1)):
        return None
    hits = _refs(m).get(m["base"] + fo) or []
    if not hits:
        return None
    score = 10.0 + min(3.0, len(hits))
    ev = {"gate": "dataval", "w": w, "nref": len(hits),
          "refs": [h.get("va") for h in hits[:4]], "fo_imm": hex(fo)}
    return score, ev
