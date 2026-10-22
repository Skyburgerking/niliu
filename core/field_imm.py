# -*- coding: utf-8 -*-
"""Organ: mov [obj+disp], imm -- single object-field constants."""
from __future__ import annotations

import re
import struct

import registry as R

_FRAME = re.compile(r"\[\s*(esp|ebp)\b", re.I)
_MEM = re.compile(r"^\[\s*(e[a-z]{2})\s*([+-])\s*(0x[0-9a-fA-F]+|\d+)\s*\]")


def _dest_mem(text):
    body = text.split(None, 1)[1] if " " in text else ""
    i = body.find("[")
    j = body.find("]", i)
    if i < 0 or j < 0:
        return None
    part = body[i:j + 1]
    if _FRAME.search(part):
        return None
    m = _MEM.search(part)
    if not m:
        return None
    txt = m.group(3)
    disp = int(txt, 16) if txt.lower().startswith("0x") else int(txt)
    if m.group(2) == "-":
        disp = -disp
    return m.group(1), disp


@R.organ("field", ["imm"],
         "mov [对象+偏移], imm —— 字段初值（排除栈帧，只认字段区）")
def organ_field(m, value, goal=None):
    import addr as AD
    ix = AD._ix(m)
    out = []
    for c in ix["byval"].get(value, []):
        if c.get("mn") != "mov" or "[" not in c.get("text", ""):
            continue
        got = _dest_mem(c["text"])
        if not got:
            continue
        base, disp = got
        if disp < 0 or disp > 0x1000:
            continue
        d = dict(c)
        d["_base"] = base
        d["_disp"] = disp
        out.append(d)
    return out


@R.gate("imm", rank=1, desc="字段写入门：对象字段上的立即数初值，独立回读确认")
def gate_imm(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    frm = int(goal.get("from") or 0) & 0xFFFFFFFF
    to = goal.get("to")
    w = int(c.get("w") or 4)
    fo = c.get("fo_imm", c.get("fo"))
    if fo is None or fo < 0 or fo + w > len(raw):
        return None
    got = int.from_bytes(raw[fo:fo + w], "little")
    if got != (frm & ((1 << (8 * w)) - 1)):
        return None
    disp = c.get("_disp")
    if disp is None:
        g = _dest_mem(c.get("text", ""))
        if not g:
            return None
        disp = g[1]
    score = 10.0
    if disp % 4 == 0 and 0x20 <= disp <= 0x400:
        score += 1.5
    if to is not None and frm:
        r = float(to) / frm
        if abs(r - round(r)) < 1e-9 and int(round(r)) in (2, 3, 4, 5, 10, 100):
            score += 1.0
    ev = {"gate": "imm", "base": c.get("_base"), "disp": hex(disp),
          "val": got, "fo_imm": hex(fo), "w": w}
    return score, ev
