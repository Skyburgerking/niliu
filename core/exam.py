# -*- coding: utf-8 -*-
"""18-paper exam harness: precision/recall of the gates against the PvZ ground truth."""
from __future__ import annotations

import json
import os
import sys

import map as M
import hunt as H


def load_truth(path="facts/pvz_current.json"):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    ops = d["ops"] if isinstance(d, dict) and "ops" in d else d
    out = []
    for o in ops:
        og, nw = bytes.fromhex(o["orig"]), bytes.fromhex(o["new"])
        if len(og) != len(nw):
            continue
        if len(og) == 1:
            out.append({"fo": o["file_off"], "kind": "u8", "a": og[0], "b": nw[0]})
        elif len(og) == 4:
            out.append({"fo": o["file_off"], "kind": "u32",
                        "a": int.from_bytes(og, "little"), "b": int.from_bytes(nw, "little")})
        elif len(og) == 8:
            out.append({"fo": o["file_off"], "kind": "f64",
                        "a": __import__("struct").unpack("<d", og)[0],
                        "b": __import__("struct").unpack("<d", nw)[0]})
    return out


def make_papers(truth, min_sites=1):
    from collections import defaultdict
    g = defaultdict(list)
    for t in truth:
        g[(t["kind"], t["a"], t["b"])].append(t["fo"])
    papers = []
    for (kind, a, b), sites in sorted(g.items(), key=lambda kv: -len(kv[1])):
        if len(sites) < min_sites:
            continue
        papers.append({"kind": kind, "from": a, "to": b, "sites": sorted(set(sites))})
    return papers


def grade(cands, truth_sites, k=None):
    got = {c["fo"] for c in cands}
    if k:
        got = {c["fo"] for c in cands[:k]}
    hit = got & set(truth_sites)
    rec = len(hit) / max(1, len(truth_sites))
    pre = len(hit) / max(1, len(got))
    f1 = 0.0 if rec + pre == 0 else 2 * rec * pre / (rec + pre)
    return {"recall": round(rec, 3), "precision": round(pre, 3), "f1": round(f1, 3),
            "hit": len(hit), "of": len(truth_sites), "returned": len(got)}


def _sig(ev):
    if not ev:
        return None
    sw = ev.get("switch")
    if not sw:
        return None
    vals = frozenset(v for xs in sw.values() for v in xs)
    return ("arm", frozenset(sw.keys()) and len(sw), tuple(sorted(vals)),
            ev.get("same_dest"))


def run_exam(exe, top=30, papers=None, cache="var/map_exam.pkl", verbose=True, out=None):
    m = M.build(exe, cache=cache)
    papers = papers if papers is not None else make_papers(load_truth())
    results = []
    for p in papers:
        w = {"u8": 1, "u32": 4, "f64": 8}[p["kind"]]
        r = H.run(exe, {"name": "%s %s->%s" % (p["kind"], p["from"], p["to"]),
                        "from": p["from"], "to": p["to"], "width": w}, rounds=4,
                  cache=cache, fresh=True)
        cands = []
        if r["pass"]:
            for c in r["best"]["cands"]:
                cands.append({"fo": int(c["fo"], 16), "text": c["text"],
                              "ev": c.get("evidence", {}), "va": c["va"]})
        sc = grade(cands, p["sites"], k=top)

        truth_sigs = set()
        for c in cands:
            if c["fo"] in p["sites"]:
                s = _sig(c["ev"])
                if s:
                    truth_sigs.add(s)
        twins = [c["fo"] for c in cands
                 if c["fo"] not in p["sites"] and _sig(c["ev"]) in truth_sigs]
        sc.update({"from": p["from"], "to": p["to"], "kind": p["kind"],
                   "sites": p["sites"][:6], "gate": ("-" if not r["pass"] else r["best"]["gate"]),
                   "twins": twins, "why": (r.get("reason") or [""])[:2] if not r["pass"] else ""})
        if twins:
            closed = (len(cands) - len(twins))
            sc["precision_closed"] = round(
                len({c["fo"] for c in cands} & set(p["sites"])) / max(1, closed), 3)
        results.append(sc)
        if verbose:
            extra = ""
            if not r["pass"]:
                extra = "  拒绝"
            elif twins:
                extra = "  同构+%d %s" % (len(twins), " ".join(hex(t) for t in twins))
            print("  %-10s %6s -> %-10s %-5s 召回 %d/%d  精确 %.2f  F1 %.2f%s%s"
                  % (p["kind"], p["from"], p["to"], sc["gate"], sc["hit"], sc["of"],
                     sc["precision"], sc["f1"],
                     "  ★满分" if sc["f1"] == 1.0 else "", extra))

    full = sum(1 for r in results if r["f1"] == 1.0)
    answered = sum(1 for r in results if r["gate"] != "-")
    got_any = sum(1 for r in results if r["hit"] > 0)
    avg = sum(r["f1"] for r in results) / max(1, len(results))
    print("\n卷子 %d 张 | 判据给出答案 %d 张 | 碰到真值 %d 张 | 满分 %d 张 | 平均 F1 %.3f"
          % (len(results), answered, got_any, full, avg))
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"exe": exe, "papers": results, "full": full,
                       "answered": answered, "avg_f1": round(avg, 3)},
                      f, ensure_ascii=False, indent=1)
        print("明细 → %s" % out)
    return results


if __name__ == "__main__":
    exe = sys.argv[1] if len(sys.argv) > 1 else "测试/PvZ_原件.exe.newniliu_bak_20261017_202317"
    only = os.environ.get("ONLY_PAPER")
    paps = None
    if only:
        a, b = only.split("->")
        paps = [p for p in make_papers(load_truth())
                if p["from"] == int(a) and p["to"] == int(b)]
        print("只考：%s" % only)
    print("试题源 facts/pvz_current.json   每张卷子都从空记忆开始\n")
    run_exam(exe, top=int(sys.argv[2]) if len(sys.argv) > 2 else 30, papers=paps,
             out="结果/考试_%s.json" % os.path.basename(exe)[:20])
