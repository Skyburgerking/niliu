# -*- coding: utf-8 -*-
"""Organ: name-anchored structure tables (stride, column, gcd, placeholders, lone votes)."""
from __future__ import annotations

import struct
from math import gcd

import rules

NAME_START = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")
NAME_BODY = NAME_START | set(b"0123456789")
FILLERS = (0xFF, 0xFFFF, 0x7F, 0xFFFFFFFF)

_CACHE_KEY = "_record_cache_v3"


def _u32(d, o):
    return int.from_bytes(d[o:o + 4], "little")


def _ident_at(d, off, min_len=3, max_len=24):
    if off < 0 or off >= len(d) - 4 or d[off] not in NAME_START:
        return None
    i = 1
    while i < max_len and off + i < len(d) and d[off + i] in NAME_BODY:
        i += 1
    if i < min_len or off + i >= len(d) or d[off + i] != 0:
        return None
    return d[off:off + i].decode("latin1")


def _ptr_ranges(m):
    out = []
    for n in (".rdata", ".text", ".data"):
        s = m["sections"].get(n)
        if s:
            out.append((s["va"], s["va"] + s["vsize"]))
    return out


def anchors(m):
    c = m.get(_CACHE_KEY)
    if c and "anchors" in c:
        return c["anchors"]
    d = bytes(m["_raw"])
    bits = m.get("bits", 32)
    pw = 8 if bits == 64 else 4
    targets = [(sec, s) for sec, s in m["sections"].items() if s.get("rsize")]
    out = {}
    for sec in (".data", ".rdata", ".text"):
        s = m["sections"].get(sec)
        if not s:
            continue
        for p in range(s["roff"], s["roff"] + s["rsize"] - pw, pw):
            v = int.from_bytes(d[p:p + pw], "little")
            if not v:
                continue
            for _tname, tsec in targets:
                if not (tsec["va"] <= v < tsec["va"] + max(tsec["vsize"], tsec["rsize"])):
                    continue
                nm = _ident_at(d, tsec["roff"] + (v - tsec["va"]))
                if nm:
                    out[p] = nm
                break
    m.setdefault(_CACHE_KEY, {})["anchors"] = out
    return out


def tables(m, strides=None, min_len=None):
    if strides is None:
        strides = rules.get("record.table_strides", list(range(8, 65, 4)))
    if min_len is None:
        min_len = rules.get("record.table_min_len", 4)
    c = m.get(_CACHE_KEY) or {}
    if "tables" in c and min_len == rules.get("record.table_min_len", 4):
        return c["tables"]
    anc = anchors(m)
    pos = sorted(anc)
    pset = set(pos)
    out = []
    used = set()
    for s in strides:
        for a in pos:
            if a in used or (a - s) in pset:
                continue
            chain = [a]
            n = a + s
            while n in pset:
                chain.append(n)
                n += s
            if len(chain) >= min_len:
                out.append({"stride": s, "anchors": chain,
                            "lo": chain[0], "hi": chain[-1],
                            "names": [anc[x] for x in chain[:4]]})
                used.update(chain)
    m.setdefault(_CACHE_KEY, {})["tables"] = out
    return out


def _col_stats(d, t, rel):
    vals = []
    for a in t["anchors"]:
        o = a + rel
        if o >= 0:
            vals.append(_u32(d, o))
    nz = [v for v in vals if v]
    if len(nz) < 3:
        return {"gcd": 1, "ratio": 0.0, "n": len(nz)}
    g = 0
    for v in nz:
        g = gcd(g, v)
        if g == 1:
            break
    ratio = sum(1 for v in nz if g > 1 and v % g == 0) / len(nz)
    return {"gcd": g, "ratio": ratio, "n": len(nz)}


def _has_filler_run(d, o, span, run=None):
    if run is None:
        run = rules.get("record.filler_run", 3)
    vals = []
    for k in range(-span, span + 4, 4):
        p = o + k
        vals.append(_u32(d, p) if 0 <= p and p + 4 <= len(d) else None)
    best, cur = 1, 1
    for i in range(1, len(vals)):
        if vals[i] is not None and vals[i] == vals[i - 1] and vals[i] in FILLERS:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best >= run


def find(m, from_value, min_gcd=None, min_ratio=None, min_lift=None,
         strong_votes=None, max_sites=None, use_filler=True, use_solo=True,
         use_table=True):
    if min_gcd is None:
        min_gcd = rules.get("record.min_gcd", 2)
    if min_ratio is None:
        min_ratio = rules.get("record.min_ratio", 0.9)
    if min_lift is None:
        min_lift = rules.get("record.min_lift", 5.0)
    if strong_votes is None:
        strong_votes = rules.get("record.strong_votes", 3)
    if max_sites is None:
        max_sites = rules.get("record.max_sites", 64)
    d = bytes(m["_raw"])
    hits, cells = set(), 0
    for sec in (".data", ".rdata"):
        dt = m["sections"].get(sec)
        if not dt or not dt.get("rsize"):
            continue
        lo, hi = dt["roff"], dt["roff"] + dt["rsize"]
        hits |= {o for o in range(lo, hi - 4, 4) if _u32(d, o) == from_value}
        cells += max(0, (hi - lo) // 4)
    if not hits:
        return None
    cells = max(1, cells)
    units = tables(m) if use_table else [{"stride": 64, "anchors": sorted(anchors(m)),
                                          "lo": 0, "hi": 0, "names": ["(全部锚点)"]}]
    cols = []
    for t in units:
        s = t["stride"]
        for delta in range(4, s + 1, 4):
          for rel in (-delta, delta):
              got = [a + rel for a in t["anchors"] if (a + rel) in hits]
              if not got:
                  continue
              if use_filler:
                  got = [o for o in got if not _has_filler_run(d, o, s)]
                  if not got:
                      continue
              expect = len(t["anchors"]) * len(hits) / cells
              lift = len(got) / max(0.01, expect)
              if lift < min_lift:
                  continue
              st = _col_stats(d, t, rel)
              if st["gcd"] < min_gcd or st["ratio"] < min_ratio:
                  continue
              cols.append({"stride": s, "delta": rel, "votes": len(got),
                           "gcd": st["gcd"], "ratio": round(st["ratio"], 2),
                           "lift": round(lift, 1), "sites": got,
                           "table": "0x%x" % t["lo"], "names": t["names"]})
    if not cols:
        return None
    if use_solo and max(c["votes"] for c in cols) >= strong_votes:
        cols = [c for c in cols if c["votes"] >= 2]
    if not cols:
        return None
    sites = {}
    for c in cols:
        ev = {"gate": "record", "stride": c["stride"], "delta": c["delta"],
              "votes": c["votes"], "gcd": c["gcd"], "lift": c["lift"],
              "table": c["table"], "table_names": c["names"]}
        score = 10.0 + min(6.0, c["votes"] * 0.5) + min(4.0, c["lift"] / 5.0)
        for o in c["sites"]:
            if o not in sites or sites[o][0] < score:
                sites[o] = (score, ev)
    cols.sort(key=lambda x: -x["votes"])
    rows = sorted(sites.items(), key=lambda kv: -kv[1][0])[:max_sites]
    return {"sites": rows, "cols": cols,
            "why": "表 %d 张，命中列 %d 条（强列票数 %d）"
                   % (len(tables(m)), len(cols),
                      max(c["votes"] for c in cols))}
