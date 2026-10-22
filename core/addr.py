# -*- coding: utf-8 -*-
"""Operand parsing: [reg +- disp], RIP-relative, scaled index, stack-frame detection."""
from __future__ import annotations

import bisect
import re

import rules

MEM = re.compile(r"^(?:dword ptr |qword ptr |word ptr |byte ptr )?"
                 r"\[([a-z0-9]+)(?: ([+-]) (0x[0-9a-f]+|\d+))?(?: \+ [a-z0-9]+\*\d+)?\]$")
STACK = ("esp", "ebp", "rsp", "rbp")
FRAME = re.compile(r"\[(?:e|r)?(?:sp|bp)(?:\s*[+-]|\])")


def _ix(m):
    ix = m.get("_ix")
    if ix:
        return ix
    ins = m["insns"]
    va = [i[0] for i in ins]
    k = {v: j for j, v in enumerate(va)}
    byval = {}
    for c in m["consts"]:
        byval.setdefault(c["imm"], []).append(c)
    for v in byval:
        byval[v].sort(key=lambda c: c["va"])

    data_lo = min((s["va"] for n, s in m["sections"].items() if n in (".rdata", ".data")),
                  default=0)
    data_hi = max((s["va"] + s["vsize"] for n, s in m["sections"].items()
                   if n in (".rdata", ".data")), default=0)
    abs_refs = sorted({c["imm"] for c in m["consts"] if data_lo <= c["imm"] < data_hi})

    ix = {"va": va, "k": k, "byval": byval,
          "data_lo": data_lo, "data_hi": data_hi, "abs_refs": abs_refs}
    m["_ix"] = ix
    return ix


def _span(ix, lo, hi):
    vas = ix["va"]
    return bisect.bisect_left(vas, lo), bisect.bisect_right(vas, hi)


def membase(text):
    mm = MEM.match(_dest(text))
    if not mm:
        return None, None
    txt = mm.group(3) or "0"
    disp = int(txt, 16) if txt.startswith("0x") else int(txt)
    if mm.group(2) == "-":
        disp = -disp
    return mm.group(1), disp


def _dest(text):
    body = text.split(" ", 1)[1] if " " in text else ""
    if "," not in body:
        return ""
    return body.rsplit(",", 1)[0].strip()


def _is_frame(text):
    return bool(FRAME.search(text))


def _shape(cands):
    return [{"va": "0x%x" % c["va"], "fo": "0x%x" % c.get("fo_imm", c["fo"]),
             "text": c["text"], "score": round(c["_s"], 2),
             "evidence": c.get("_ev", {})} for c in cands]


def _acc_origin(m, ix, va, ahead=None, back=None):
    if ahead is None:
        ahead = rules.get("arm.acc_ahead", 20)
    if back is None:
        back = rules.get("arm.acc_back", 60)
    ins = m["insns"]
    k = ix["k"].get(va)
    if k is None:
        return None
    reg = _dest(ins[k][1] + " " + ins[k][2]).strip()
    if not reg:
        return None
    acc = None
    for j in range(k + 1, min(len(ins), k + ahead)):
        mn, op = ins[j][1], ins[j][2]
        if mn != "add" or "," not in op:
            continue
        dst, src = [x.strip() for x in op.rsplit(",", 1)]
        if src == reg and dst != reg and "." not in dst:
            acc = dst
            break
    if not acc:
        return None
    for j in range(k, max(0, k - back), -1):
        mn, op = ins[j][1], ins[j][2]
        if "," not in op:
            continue
        dst = op.rsplit(",", 1)[0].strip()
        if dst != acc:
            continue
        src = op.rsplit(",", 1)[1].strip()
        if mn == "xor" and src == acc:
            return "pure"
        if mn == "mov" and (src in ("0", "0x0")):
            return "pure"
        if mn == "mov" and "[" in src:
            return "derived"
        return None
    return None


index = _ix
span = _span
dest = _dest
is_frame = _is_frame
shape = _shape
acc_origin = _acc_origin
