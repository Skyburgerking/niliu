# -*- coding: utf-8 -*-
"""Organ: f32 constants addressed by byte substitution."""
from __future__ import annotations

import math
import struct

import registry as R

SECTIONS = (".text", ".rdata", ".data")
LO, HI = 0.02, 300.0


def _clean(v):
    if not math.isfinite(v):
        return False
    a = abs(v)
    if a < LO or a > HI:
        return False
    x = v * 1000.0
    return abs(x - round(x)) < 0.6


def _refs(m):
    got = m.get("_f32_refs")
    if got is not None:
        return got
    d = bytes(m["_raw"])
    sec = m["sections"].get(".text")
    base = m["base"]
    s = set()
    if sec:
        lo, hi = sec["roff"], sec["roff"] + sec["rsize"]
        for o in range(lo, hi - 4):
            s.add(int.from_bytes(d[o:o + 4], "little"))
    m["_f32_refs"] = s
    return s


def index(m):
    got = m.get("_f32_index")
    if got is not None:
        return got
    d = bytes(m["_raw"])
    base = m["base"]
    refs = _refs(m)
    out = []
    for name in SECTIONS:
        sec = m["sections"].get(name)
        if not sec:
            continue
        lo, hi = sec["roff"], sec["roff"] + sec["rsize"]
        for o in range(lo, hi - 4):
            try:
                v = struct.unpack_from("<f", d, o)[0]
            except Exception:
                continue
            if not _clean(v):
                continue
            if (base + o) not in refs:
                continue
            out.append((o, v))
    m["_f32_index"] = out
    return out


@R.organ("f32", ["f32"], "f32 常量：4 字节 float，改其中一个字节（typed 缺的 <f 那一列）",
        self_gated=False)
def organ_f32(m, value, goal=None):
    goal = goal or {}
    to = goal.get("to")
    if to is None:
        return []
    raw = bytes(m["_raw"])
    out = []
    for o, v in index(m):
        chunk = bytearray(raw[o:o + 4])
        for k in range(4):
            if chunk[k] != (value & 0xFF):
                continue
            tmp = bytearray(chunk)
            tmp[k] = int(to) & 0xFF
            nv = struct.unpack("<f", bytes(tmp))[0]
            if not _clean(nv) or abs(nv - v) < 1e-6:
                continue
            out.append({
                "va": m["base"] + o + k, "fo": o + k, "fo_imm": o + k,
                "imm": value & 0xFF, "mn": "f32",
                "text": "f32 @0x%x 第%d字节 (%.4f)" % (o, k, v),
                "_f32_at": o, "_fmt": "<f", "_width": 4,
                "_f32_before": v, "_f32_after": nv, "_byte": k,
            })
    return out


@R.gate("f32", rank=1, prune="mirror",
        desc="f32 门：独立回读 4 字节、重算替换前后的值、两边都必须是像样的常量")
def gate_f32(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    o = c.get("_f32_at")
    k = c.get("_byte")
    to = goal.get("to")
    if o is None or k is None or to is None:
        return None
    if o < 0 or o + 4 > len(raw):
        return None
    before = struct.unpack_from("<f", raw, o)[0]
    chunk = bytearray(raw[o:o + 4])
    if chunk[k] != goal.get("from"):
        return None
    chunk[k] = int(to) & 0xFF
    after = struct.unpack("<f", bytes(chunk))[0]
    if not (_clean(before) and _clean(after)):
        return None
    ratio = after / before if before else 0.0
    score = 10.0
    if abs(abs(ratio) - 2.0) < 1e-6 or abs(abs(ratio) - 0.5) < 1e-6:
        score += 3.0
    if abs(after * 100 - round(after * 100)) < 0.6:
        score += 0.5
    ev = {"gate": "f32", "f32": [round(before, 5), round(after, 5)], "byte": k,
          "ratio": round(ratio, 4), "text": c.get("text")}
    return score, ev
