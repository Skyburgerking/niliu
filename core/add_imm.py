# -*- coding: utf-8 -*-
"""Organ: add/sub [obj+disp], imm -- per-event decrements (damage per bite, etc.)."""
from __future__ import annotations

import struct

import addr as AD
import registry as R

_OPS = ("add", "sub")


def _sval(imm, w):
    m = (1 << (8 * w)) - 1
    v = imm & m
    if w == 1 and v >= 0x80:
        return v - 0x100
    if w == 2 and v >= 0x8000:
        return v - 0x10000
    if w == 4:
        return struct.unpack("<i", struct.pack("<I", v))[0]
    return v


@R.organ("addfield", ["addimm"],
         "add/sub [对象+偏移], imm —— 扣减/累加型常量（咬伤、计时递减）")
def organ_addfield(m, value, goal=None):
    want = abs(int(value or 0))
    out = []
    for c in m["consts"]:
        if c.get("mn") not in _OPS or c.get("idx") != 1:
            continue
        text = c.get("text", "")
        if "[" not in text:
            continue
        dest = AD._dest(text)
        if "[" not in dest:
            continue
        base, disp = AD.membase(text)
        if not base or base in AD.STACK:
            continue
        if disp is None or disp < -0x1000 or disp > 0x1000:
            continue
        if want:
            w = int(c.get("w") or 1)
            if abs(_sval(int(c.get("imm") or 0), w)) != want:
                continue
        d = dict(c)
        d["_base"] = base
        d["_disp"] = disp
        out.append(d)
    return out


@R.gate("addimm", rank=1, desc="扣减型常量门：add/sub [对象+偏移], imm，独立回读 + 符号解释")
def gate_addimm(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    frm = int(goal.get("from") or 0)
    to = goal.get("to")
    w = int(c.get("w") or 1)
    fo = c.get("fo_imm", c.get("fo"))
    if fo is None or fo < 0 or fo + w > len(raw):
        return None

    got = int.from_bytes(raw[fo:fo + w], "little")
    mask = (1 << (8 * w)) - 1
    if got != (int(c.get("imm") or 0) & mask):
        return None
    sv = _sval(got, w)
    if not frm:
        return None
    if abs(sv) != abs(frm) and sv != frm and (got & 0xFFFFFFFF) != (frm & 0xFFFFFFFF):
        return None

    disp = c.get("_disp")
    if disp is None:
        g = AD.membase(c.get("text", ""))
        disp = g[1] if g else 0
    score = 10.0
    if disp % 4 == 0 and 0x20 <= disp <= 0x400:
        score += 1.5
    if to is not None and frm and to:
        try:
            r = float(to) / float(frm)
        except ZeroDivisionError:
            r = 0
        if abs(r - round(r)) < 1e-9 and int(round(r)) in (2, 3, 4, 5, 10, 100):
            score += 1.0
    if c.get("mn") == "add" and sv == -abs(frm):
        score += 0.5

    ev = {"gate": "addimm", "op": c.get("mn"), "base": c.get("_base"),
          "disp": hex(disp), "val": sv, "fo_imm": hex(fo), "w": w,
          "byte": ("0x%02x" % got) + ("（= %d）" % sv if sv < 0 else "")}
    return score, ev
