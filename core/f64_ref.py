# -*- coding: utf-8 -*-
"""Organ: code-referenced f64 multipliers (0.4, 0.25, ...) addressed by byte value."""
from __future__ import annotations

import math
import struct

import addr as AD
import registry as R


def _refs(m):
    got = m.get("_typedref_refs")
    if got is not None:
        return got
    ix = AD._ix(m)
    refs = set(ix["abs_refs"])
    m["_typedref_refs"] = refs
    return refs


def _floatable(v):
    if not math.isfinite(v) or abs(v) > 1000.0 or abs(v) < 1e-6:
        return False
    try:
        f = struct.unpack("<f", struct.pack("<f", v))[0]
    except (OverflowError, ValueError):
        return False
    return f == v


def _window_ok(v):
    if not math.isfinite(v) or abs(v) > 1000.0 or abs(v) < 1e-6:
        return False
    return abs(v - round(v, 3)) <= 1e-6


@R.organ("f64ref", ["typedref"],
         "被代码引用的 f64 倍率常量（0.4/0.5/1.5 这类非整数）")
def organ_f64ref(m, value, goal=None):
    goal = goal or {}
    to = goal.get("to")
    if to is None:
        return []
    raw = bytes(m["_raw"])
    refs = _refs(m)
    base = m["base"]
    out = []
    for name in (".rdata", ".data"):
        sec = m["sections"].get(name)
        if not sec:
            continue
        lo, hi = sec["roff"], min(sec["roff"] + sec["rsize"], len(raw) - 8)
        for o in range(lo - lo % 8, hi, 8):
            if not _window_ok(struct.unpack_from("<d", raw, o)[0]):
                continue
            chunk = raw[o:o + 8]
            if chunk.count(value & 0xFF) == 0:
                continue
            for k in range(8):
                if chunk[k] != (value & 0xFF):
                    continue
                tmp = bytearray(chunk)
                tmp[k] = int(to) & 0xFF
                before = struct.unpack("<d", chunk)[0]
                after = struct.unpack("<d", bytes(tmp))[0]
                if not (_window_ok(before) and _window_ok(after)):
                    continue
                if abs(after - before) < 1e-12:
                    continue
                out.append({
                    "va": base + o + k, "fo": o + k, "fo_imm": o + k,
                    "imm": value, "mn": "f64",
                    "text": "f64 @%#x 第%d字节  %r→%r" % (o, k, before, after),
                    "_f64_at": o, "_f64_before": before, "_f64_after": after,
                    "_byte": k,
                })
    return out


@R.gate("typedref", rank=1,
        desc="被引用的 f64 倍率常量门：独立回读 8 字节、重算前后值、必须被 .text 引用")
def gate_typedref(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    o, k = c.get("_f64_at"), c.get("_byte")
    to = goal.get("to")
    if o is None or k is None or to is None or o < 0 or o + 8 > len(raw):
        return None
    before = struct.unpack_from("<d", raw, o)[0]
    chunk = bytearray(raw[o:o + 8])
    if chunk[k] != int(goal.get("from") or 0) & 0xFF:
        return None
    chunk[k] = int(to) & 0xFF
    after = struct.unpack("<d", bytes(chunk))[0]
    if not (_window_ok(before) and _window_ok(after)):
        return None
    ratio = (after / before) if before else 0.0
    score = 11.0
    if _floatable(before) or _floatable(after):
        score += 1.0
    if (m["base"] + o) in _refs(m):
        score += 2.0
    if abs(ratio - 0.25) < 1e-3 or abs(ratio - 0.5) < 1e-3 or abs(ratio - 2.0) < 1e-3:
        score += 1.0
    ev = {"gate": "typedref", "f64": [before, after], "byte": k,
          "ratio": round(ratio, 4), "ref": hex(m["base"] + o), "text": c.get("text")}
    return score, ev
