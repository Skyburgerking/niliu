# -*- coding: utf-8 -*-
"""Organ: f64 constants addressed by byte substitution."""
from __future__ import annotations

import math
import struct

import registry as R
import rules

SECTIONS = (".text", ".rdata", ".data")
MULTS = (10, 5)


def _nice(v):
    if not math.isfinite(v) or abs(v - round(v)) > 1e-9:
        return False
    a = abs(v)
    if a < 1 or a > 1e6:
        return False
    return any(abs(v) % m == 0 for m in MULTS)


def index(m):
    got = m.get("_typed_index")
    if got is not None:
        return got
    d = bytes(m["_raw"])
    out = []
    for name in SECTIONS:
        sec = m["sections"].get(name)
        if not sec:
            continue
        lo, hi = sec["roff"], sec["roff"] + sec["rsize"]
        for o in range(lo, hi - 8):
            try:
                v = struct.unpack_from("<d", d, o)[0]
            except Exception:
                continue
            if _nice(v):
                out.append((o, v))
    m["_typed_index"] = out
    return out


@R.organ("typed", ["typed"], "类型化常量：改的是一个 f64/整数的某几个字节（scanmem 的 value_t 思路）",
        self_gated=False)
def organ_typed(m, value, goal=None):
    goal = goal or {}
    to = goal.get("to")
    if to is None:
        return []
    raw = bytes(m["_raw"])
    out = []
    for o, v in index(m):
        chunk = bytearray(raw[o:o + 8])
        for k in range(8):
            if chunk[k] != value:
                continue
            tmp = bytearray(chunk)
            tmp[k] = int(to) & 0xFF
            try:
                nv = struct.unpack("<d", bytes(tmp))[0]
            except Exception:
                continue
            if not _nice(nv) or abs(nv - v) < 1e-9:
                continue
            out.append({
                "va": m["base"] + o + k, "fo": o + k, "fo_imm": o + k,
                "imm": value, "mn": "f64", "text": "f64 @0x%x 第%d字节" % (o, k),
                "_f64_at": o, "_f64_before": v, "_f64_after": nv, "_byte": k,
            })
    return out


@R.gate("typed", rank=1, prune="mirror",
        desc="类型化常量门：独立回读 8 字节、重算替换前后的值、必须两边都像样")
def gate_typed(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    o = c.get("_f64_at")
    k = c.get("_byte")
    to = goal.get("to")
    if o is None or k is None or to is None:
        return None
    if o < 0 or o + 8 > len(raw):
        return None
    before = struct.unpack_from("<d", raw, o)[0]
    chunk = bytearray(raw[o:o + 8])
    if chunk[k] != goal.get("from"):
        return None
    chunk[k] = int(to) & 0xFF
    after = struct.unpack("<d", bytes(chunk))[0]
    if not (_nice(before) and _nice(after)):
        return None
    ratio = after / before if before else 0.0
    score = 10.0
    if abs(after) % 100 == 0:
        score += 2.0
    if abs(abs(ratio) - 0.5) < 1e-9 or abs(abs(ratio) - 2.0) < 1e-9:
        score += 1.0
    ev = {"gate": "typed", "f64": [before, after], "byte": k,
          "ratio": round(ratio, 4), "text": c.get("text")}
    return score, ev
