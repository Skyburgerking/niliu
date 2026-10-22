# -*- coding: utf-8 -*-
"""Organ: inc/dec [obj+disp] counters."""
from __future__ import annotations

import registry as R

_STACK = ("esp", "ebp", "rsp", "rbp")


def _cands(m):
    got = m.get("_incdec_cands")
    if got is not None:
        return got
    raw = bytes(m["_raw"])
    out = []
    for va, mn, ops, size, fo in m["insns"]:
        if mn not in ("inc", "dec"):
            continue
        if "[" not in ops or "ptr" not in ops:
            continue
        disp = 0
        base = None
        if "+" in ops:
            try:
                disp = int(ops.split("+")[-1].rstrip("] "), 16)
            except ValueError:
                disp = 0
            base = ops.split("[")[-1].split(" ")[0].strip()
        elif "[" in ops:
            base = ops.split("[")[-1].split("]")[0].strip()
        if base in _STACK or disp > 0x1000:
            continue
        width = 1 if "byte ptr" in ops else 4
        modrm_fo = fo + (1 if raw[fo] in (0xFE, 0xFF) and raw[fo + 1] & 0xC0 != 0xC0 else 0)
        out.append({"va": va, "fo": modrm_fo, "fo_imm": modrm_fo, "imm": 1 if mn == "inc" else 0xFF,
                    "mn": mn, "text": "%s %s" % (mn, ops), "w": width,
                    "_base": base, "_disp": disp, "_kind": mn})
    m["_incdec_cands"] = out
    return out


@R.organ("incdec", ["incdec"], "inc/dec 内存操作数（每帧 +1/-1 的计数器）")
def organ_incdec(m, value, goal=None):
    out = []
    for c in _cands(m):
        if value not in (1, 0xFF, 0):
            continue
        out.append(dict(c))
    return out


@R.gate("incdec", rank=1, desc="inc/dec 门：ModRM reg 位复核 + 目的非栈帧")
def gate_incdec(m, c, goal, window=0):
    raw = bytes(m["_raw"])
    fo = c.get("fo_imm")
    if fo is None or fo < 0 or fo + 1 > len(raw):
        return None
    modrm = raw[fo]
    if raw[fo - 1] not in (0xFE, 0xFF) and fo > 0:
        return None
    reg = (modrm >> 3) & 7
    kind = "dec" if reg == 1 else ("inc" if reg == 0 else None)
    if kind is None or kind != c.get("_kind"):
        return None
    if (modrm >> 6) == 3:
        return None
    ev = {"gate": "incdec", "kind": kind, "base": c.get("_base"),
          "disp": hex(int(c.get("_disp") or 0)), "width": c.get("w")}
    return 9.0, ev
