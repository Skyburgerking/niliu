# -*- coding: utf-8 -*-
"""Organ: anonymous type tables (value column followed by an incrementing id column)."""
from __future__ import annotations

import registry as R

_STRIDES = (8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48)
_MIN_RUN = 6
_MAX_RUN = 96


def _u32(raw, p):
    return int.from_bytes(raw[p:p + 4], "little")


def _run(raw, p, stride, hi):
    n, prev = 0, None
    q = p
    while q + stride <= hi and n < _MAX_RUN:
        v = _u32(raw, q)
        ident = _u32(raw, q + 4)
        if v < 0 or v > 0x7FFFFFFF:
            break
        if prev is None:
            if not (0 < ident < 0x100000):
                break
        elif ident != prev + 1:
            break
        prev = ident
        n += 1
        q += stride
    return n


def _tables(m, value):
    raw = bytes(m["_raw"])
    found = []
    for name, s in m["sections"].items():
        if name not in (".data", ".rdata"):
            continue
        lo = s["roff"]
        hi = min(s["roff"] + s["rsize"], len(raw))
        for p in range(lo, hi - 8, 4):
            if _u32(raw, p) != value:
                continue
            for stride in _STRIDES:
                n = _run(raw, p, stride, hi)
                if n >= _MIN_RUN:
                    found.append((p, stride, n))
    best = {}
    for p, stride, n in found:
        key = (p, stride)
        if best.get(key, (0,))[0] < n:
            best[key] = (n,)
    rows = []
    for (p, stride), (n,) in best.items():
        for i in range(n):
            rows.append((p + i * stride, stride, n, i))
    return rows


@R.organ("idtable", ["idtable"],
         "匿名类型表：值列后跟递增 id 列（步长 8~48），按表回站点")
def organ_idtable(m, value, goal=None):
    if not value:
        return []
    out = []
    for fo, stride, n, idx in _tables(m, int(value)):
        v = int.from_bytes(bytes(m["_raw"])[fo:fo + 4], "little")
        out.append({"va": m["base"] + fo, "imm": v, "mn": "data",
                    "text": ".data[%#x] = %d（表 %d 条，第 %d 条）" % (fo, v, n, idx),
                    "fo": fo, "fo_imm": fo, "w": 4,
                    "_base": "table", "_disp": 0,
                    "_tbl": (fo - idx * stride, stride, n, idx)})
    return out


@R.gate("idtable", rank=1, desc="匿名类型表门：值列 + 递增 id 列，独立回读确认")
def gate_idtable(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    frm = int(goal.get("from") or 0)
    to = goal.get("to")
    fo = c.get("fo_imm", c.get("fo"))
    if not frm or fo is None or fo < 0 or fo + 4 > len(raw):
        return None
    got = int.from_bytes(raw[fo:fo + 4], "little")
    if got != (int(c.get("imm") or 0) & 0xFFFFFFFF):
        return None

    tbl, stride, n, idx = c.get("_tbl") or (0, 0, 0, 0)
    if stride < 8 or n < _MIN_RUN:
        return None
    hits = sum(1 for i in range(n) if _u32(raw, tbl + i * stride) == (frm & 0xFFFFFFFF))
    if not hits:
        return None

    score = 12.0 + min(4.0, n / 8.0) + min(2.0, hits / 4.0)
    if to is not None and got:
        try:
            r = float(to) / float(got)
        except ZeroDivisionError:
            r = 0
        if abs(r - round(r)) < 1e-9 and int(round(r)) in (2, 3, 4, 5, 10, 100):
            score += 1.0
    ev = {"gate": "idtable", "table": hex(tbl), "stride": stride, "n": n,
          "idx": idx, "val": got, "fo_imm": hex(fo), "w": 4, "hits_from": hits,
          "ids": [_u32(raw, tbl + i * stride + 4) for i in range(min(n, 16))]}
    return score, ev
