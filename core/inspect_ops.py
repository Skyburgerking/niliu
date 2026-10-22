# -*- coding: utf-8 -*-
"""Read-only inspection ops: near / refs / explain."""
from __future__ import annotations

import map as M


def _m(self, req):
    m = getattr(self, "m", None)
    if m is not None:
        return m
    exe = req.get("exe")
    if not exe:
        return None
    return M.build(exe)


def near(m, va, n=16):
    rows = []
    for iva, mn, ops, size, fo in m["insns"]:
        if iva < va:
            continue
        if len(rows) >= n:
            break
        rows.append({"va": hex(iva), "mn": mn, "ops": ops,
                     "bytes": bytes(m["_raw"][fo:fo + size]).hex()})
    return rows


def refs(m, va):
    ins = list(m["insns"])
    hits = [i for i, (iva, mn, ops, size, fo) in enumerate(ins)
            if mn in ("call", "jmp") and ops.strip().lower() == hex(va).lower()]
    out = []
    for i in hits:
        ctx = []
        for j in range(max(0, i - 6), i):
            iva, mn, ops, size, fo = ins[j]
            ctx.append("%s %s %s" % (hex(iva), mn, ops))
        out.append({"site": hex(ins[i][0]),
                    "target": hex(va),
                    "ctx": ctx})
    return out


def explain(m, site):
    fo = site if site < 0x400000 else site - 0x400000
    va = fo + 0x400000
    row = None
    for iva, mn, ops, size, f in m["insns"]:
        if iva == va:
            row = {"va": hex(iva), "mn": mn, "ops": ops,
                   "bytes": bytes(m["_raw"][f:f + size]).hex(), "fo": hex(f)}
            break
    if row is None:
        for iva, mn, ops, size, f in m["insns"]:
            if iva <= va < iva + size:
                row = {"va": hex(iva), "mn": mn, "ops": ops,
                       "bytes": bytes(m["_raw"][f:f + size]).hex(), "fo": hex(f),
                       "imm_in": hex(va - iva)}
                break
    field = None
    if row and "[" in row["ops"] and "+" in row["ops"]:
        base = row["ops"].split("[")[-1].split(" ")[0]
        try:
            disp = int(row["ops"].split("+")[-1].split("]")[0].strip(), 16)
        except ValueError:
            disp = None
        field = {"base": base, "disp": hex(disp) if disp is not None else None}
    out = {"ok": True, "op": "explain", "site": hex(fo), "va": hex(va),
           "insn": row, "field": field,
           "window": near(m, va, 5) if row else [],
           "refs": refs(m, va) if row else []}
    if row is None:
        chunk = bytes(m["_raw"][fo:fo + 8])
        out["data"] = chunk.hex()
        out["insn"] = None
    try:
        import mapbook
        book = mapbook.collect()
        hits = [k for k, v in book.items()
                if any(o["site"] == fo for o in v["ops"])]
        out["archived"] = hits
    except Exception:
        out["archived"] = []
    return out
