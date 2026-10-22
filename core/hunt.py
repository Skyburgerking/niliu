# -*- coding: utf-8 -*-
"""Main pipeline: recon -> enum -> rank -> refine; merges organ evidence, ranks by GEDA."""
from __future__ import annotations

import bisect
import json
import re
import struct
import sys
import zlib

import addr as AD
import map as M
import registry as R
import tick as T
import tree as TR
import typed
import typed32  # noqa: F401
import field_imm
import add_imm
import id_table
import f64_ref
import inc_dec
import data_val
from klass import (CODE_MIN_SITES, pick_class as _pick_class,
                   class_state as _class_state, selfcheck as _selfcheck)
import rules
from geda import GedaCore

_ix = AD._ix
_span = AD._span
_dest = AD._dest
_is_frame = AD._is_frame
_shape = AD._shape
_acc_origin = AD._acc_origin

BASES = ["A", "G", "C", "T", "X"]
BASES_IDX = {b: i for i, b in enumerate(BASES)}

PRODUCERS = {"mov", "lea", "and", "or", "xor"}
JCC = {"je", "jne", "jz", "jnz", "jg", "jl", "jle", "jge",
       "ja", "jb", "jae", "jbe", "js", "jns", "jo", "jno"}
FRAME = re.compile(r"\[(?:e|r)?(?:sp|bp)(?:\s*[+-]|\])")
CMP_OPS = re.compile(r"^(.+?), (0x[0-9a-f]+|-?\d+)$")
BR_TARGET = re.compile(r"^0x([0-9a-f]+)$")

ORGANS_ORDER = ["record", "store", "reg", "lea", "data"]
GATES_ORDER = list(rules.get("gates_order", ["record", "arm"]))
WINDOWS = list(rules.get("windows", [24, 32, 48, 64, 96]))


def _chains(m, ix, lo, hi):
    ins = m["insns"]
    a, b = _span(ix, lo, hi)
    out = {}
    for j in range(a, min(b, len(ins) - 1)):
        if ins[j][1] != "cmp":
            continue
        mm = CMP_OPS.match(ins[j][2])
        if not mm:
            continue
        subj, val = mm.group(1).strip(), mm.group(2)
        v = int(val, 16) if val.startswith("0x") else int(val)
        if not (0 <= v < 0x100):
            continue
        if not any(ins[t][1] in JCC for t in range(j + 1, min(len(ins), j + 3))):
            continue
        out.setdefault(subj, []).append((j, v))
    return {s: xs for s, xs in out.items()
            if len(xs) >= 2 and len({v for _, v in xs}) >= 2}


def _arm_member(m, ix, k, lo, hi):
    ins = m["insns"]
    va = ins[k][0]
    a, b = _span(ix, lo, hi)
    for j in range(a, min(b, k)):
        if ins[j][1] not in JCC:
            continue
        mm = BR_TARGET.match(ins[j][2])
        if mm and int(mm.group(1), 16) == va:
            return True
        if k - j <= 3:
            return True
    return False


def gate_arm(m, c, goal, window=48):
    to = goal.get("to")
    if to is None or to == goal.get("from"):
        return None
    if c["mn"] not in PRODUCERS:
        return None
    if _is_frame(c["text"]):
        return None
    ix = _ix(m)
    k = ix["k"].get(c["va"])
    if k is None:
        return None
    lo, hi = c["va"] - window, c["va"] + window
    ch = _chains(m, ix, lo, hi)
    if not ch:
        return None
    if not _arm_member(m, ix, k, lo, hi):
        return None

    dest = _dest(c["text"])
    sib, same_dest, sib_in_arm = [], False, False
    for d in ix["byval"].get(to, []):
        if d["mn"] not in PRODUCERS or abs(d["va"] - c["va"]) > window:
            continue
        if _is_frame(d["text"]):
            continue
        sib.append(d)
        if dest and _dest(d["text"]) == dest:
            same_dest = True
        j = ix["k"].get(d["va"])
        if j is not None and _arm_member(m, ix, j, lo, hi):
            sib_in_arm = True
    if not sib:
        return None

    arms = max(len(v) for v in ch.values())
    score = 10.0
    if arms >= 3:
        score += 2.0
    if same_dest:
        score += 2.0
    if sib_in_arm:
        score += 1.0
    acc = _acc_origin(m, ix, c["va"])
    if acc == "pure":
        score += rules.get("arm.acc_pure_bonus", 1.5)
    elif acc == "derived":
        score -= rules.get("arm.acc_derived_penalty", 3.0)
    ev = {"gate": "arm", "arms": arms,
          "switch": {s: [v for _, v in xs] for s, xs in ch.items()},
          "sibling": [hex(d["va"]) for d in sib][:3], "same_dest": same_dest,
          "acc": acc}
    return score, ev



def gate_pair(m, c, goal, window=32):
    to = goal.get("to")
    if to is None:
        return None
    ix = _ix(m)
    sib = [d for d in ix["byval"].get(to, [])
           if abs(d["va"] - c["va"]) <= window]
    if not sib:
        return None
    return 4.0, {"gate": "pair", "sibling": [hex(d["va"]) for d in sib][:3]}


def _sane(v, lo=0, hi=0x100000):
    return lo <= v <= hi


STRIDES = (8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64)


def _u32(data, o):
    if o < 0 or o + 4 > len(data):
        return None
    return int.from_bytes(data[o:o + 4], "little")


def gate_table(m, c, goal, span=16):
    data = bytes(m["_raw"])
    fo = c["fo"]
    width = goal.get("width", 1)
    ix = _ix(m)
    hits = organ_data(m, goal["from"], width)
    same = sorted({h["fo"] for h in hits if abs(h["fo"] - fo) <= 0x4000})
    if len(same) < 3:
        return None

    best = None
    for stride in STRIDES:
        if stride < width:
            continue
        peers = [o for o in same if o != fo and (o - fo) % stride == 0]
        if len(peers) < 2:
            continue
        solid = 0
        for o in [fo] + peers[:6]:
            fields = [_u32(data, o + k) for k in (4, 8, 0xc)]
            if all(v is not None and 0 < v < 0x100000 for v in fields):
                solid += 1
        if solid < 2:
            continue
        va = m["base"] + fo
        refs = [r for r in ix["abs_refs"]
                if r <= va <= r + 0x4000 and (va - r) % stride == 0]
        ev = {"gate": "table", "stride": stride, "copies": len(peers) + 1,
              "solid": solid, "base_ref": hex(refs[-1]) if refs else None,
              "refs": len(refs)}
        score = 8.0 + min(4.0, len(peers)) + (2.0 if refs else 0.0)
        if best is None or score > best[0]:
            best = (score, ev)
    return best


GATES = {"arm": gate_arm, "table": gate_table}


def prune_for_gate(gate, uniq):
    if R.GATES.get(gate, {}).get("prune") == "mirror":
        groups = {}
        for k2, c2 in uniq.items():
            f2 = (c2.get("_ev") or {}).get("f64") or [0, 0]
            groups.setdefault((abs(f2[0]), abs(f2[1])), []).append((k2, c2, f2[0]))
        keep = {}
        for _g, items in groups.items():
            pos = [it for it in items if it[2] > 0]
            pick = pos if pos else items
            for k2, c2, _v in pick:
                keep[k2] = c2
        uniq = keep
    if R.GATES.get(gate, {}).get("prune") == "acc":
        accs = [c.get("_ev", {}).get("acc") for c in uniq.values()]
        if "pure" in accs and "derived" in accs:
            uniq = {k: v for k, v in uniq.items()
                    if v.get("_ev", {}).get("acc") != "derived"}
    return uniq


WINDOWLESS = R.WINDOWLESS
lead_of = R.lead_of


def gate_fn(name):
    spec = R.GATES.get(name)
    if isinstance(spec, dict) and callable(spec.get("fn")):
        return spec["fn"]
    return GATES.get(name)
GATE_MIN = {"arm": rules.get("arm.gate_min", 10.0), "table": 9.0,
            "typed": rules.get("typed.gate_min", 10.0)}
GATE_RANK = {"record": 4, "arm": 3, "table": 2, "pair": 1}


_DATA_CACHE = {}


def organ_record(m, value, **_):
    import record_table as RT
    r = RT.find(m, value)
    if not r:
        return []
    out = []
    for fo, (score, ev) in r["sites"]:
        out.append({"va": m["base"] + fo, "fo": fo, "fo_imm": fo,
                    "imm": value, "mn": "record", "idx": 0, "nops": 0,
                    "text": ".data[0x%x] = %s" % (fo, value),
                    "_s": score, "_ev": ev})
    return out


def organ_data(m, value, width=1):
    key = (id(m), value, width)
    if key in _DATA_CACHE:
        return _DATA_CACHE[key]
    if width == 8:
        needles = [struct.pack("<d", float(value))]
    else:
        needles = [int(value).to_bytes(width, "little", signed=False)]
        if width != 4 and 0 <= int(value) < 0x100000000:
            needles.append(int(value).to_bytes(4, "little", signed=False))
    data = bytes(m["_raw"])
    out = []
    for name, sec in m["sections"].items():
        if name not in (".rdata", ".data"):
            continue
        lo, hi = sec["roff"], sec["roff"] + sec["rsize"]
        for needle in needles:
            w = len(needle)
            i = data.find(needle, lo, hi)
            while i != -1:
                out.append({"va": m["base"] + i, "fo": i, "fo_imm": i, "w": w,
                            "imm": value, "mn": "data", "idx": 0, "nops": 0,
                            "text": "%s[0x%x] = %s" % (name, i, value)})
                i = data.find(needle, i + 1, hi)
                if len(out) > 20000:
                    _DATA_CACHE[key] = out
                    return out
    _DATA_CACHE[key] = out
    return out


def _organ_ok(organ, c):
    fn = R.ORGANS.get(organ, {}).get("accept")
    return bool(fn and fn(c))


def _reg_organ_record(m, value, goal=None):
    return organ_record(m, value)


def _reg_organ_data(m, value, goal=None):
    return organ_data(m, value, (goal or {}).get("width", 1))


def _make_code_organ(which):
    def fn(m, value, goal=None):
        ix = _ix(m)
        return [c for c in ix["byval"].get(value, []) if _organ_ok(which, c)]
    return fn


R.organ("record", ["record"], "认表认列：值落在结构表的同一列（公因数/占位/孤证三重筛）",
        self_gated=True)(
    _reg_organ_record)
R.organ("store", ["arm"], "mov [mem], imm —— 字段写（对象初值、血量、数量）",
        accept=lambda c: c["mn"] == "mov" and "[" in c["text"])(
    _make_code_organ("store"))
R.organ("reg", ["arm"], "mov reg, imm —— 寄存器常数（分档开关的值）",
        accept=lambda c: c["mn"] == "mov" and "[" not in c["text"])(
    _make_code_organ("reg"))
R.organ("lea", ["arm"], "lea —— 取址（基址 + n×步长 的引用）",
        accept=lambda c: c["mn"] == "lea")(
    _make_code_organ("lea"))
R.organ("data", ["table"], "数据段原始字节（不认指令，只认值和宽度）",
        reshape="data")(
    _reg_organ_data)

ORGANS_ORDER = list(R.ORGANS)


def _cands(m, organ, value, goal):
    o = R.ORGANS.get(organ)
    if not o:
        return []
    return o["fn"](m, value, goal) or []


def evaluate(m, goal, organ, gate, window=48):
    spec = R.ORGANS.get(organ, {})
    if gate not in spec.get("gates", set()):
        return {"pass": False, "why": "%s 器官不回答 %s 判据" % (organ, gate),
                "cands": [], "fitness": 0.0, "organ": organ, "gate": gate}
    cands = _cands(m, organ, goal["from"], goal)
    if not cands:
        return {"pass": False, "why": "%s 器官没有候选" % organ,
                "cands": [], "fitness": 0.0, "organ": organ, "gate": gate}
    if len(cands) > 20000:
        return {"pass": False, "why": "%s 器官命中 %d 处，超界" % (organ, len(cands)),
                "cands": [], "fitness": 0.0, "organ": organ, "gate": gate}
    if spec.get("self_gated"):
        passed = sorted(cands, key=lambda x: -x["_s"])
        return {"pass": True, "why": "record 门 %d 处" % len(passed),
                "cands": passed, "fitness": 1.0, "organ": organ, "gate": gate}

    fn = gate_fn(gate)
    if fn is None:
        return {"pass": False, "why": "%s 判据没有实现" % gate,
                "cands": [], "fitness": 0.0, "organ": organ, "gate": gate}
    passed = []
    for c in cands:
        r = fn(m, c, goal, window)
        if r is None:
            continue
        s, ev = r
        if spec.get("reshape") == "data":
            c = {"va": m["base"] + c["fo"], "fo": c["fo"], "fo_imm": c["fo"],
                 "imm": goal["from"], "mn": "data", "text": c["text"]}
        d = dict(c)
        d["_s"] = s
        d["_ev"] = ev
        passed.append(d)

    need = GATE_MIN.get(gate, 0.0)
    passed = [c for c in passed if c["_s"] >= need]
    if not passed:
        return {"pass": False,
                "why": "%s 门不过：%s 器官 %d 个候选，没有一个满足判据"
                       % (gate, organ, len(cands)),
                "cands": [], "fitness": 0.0, "organ": organ, "gate": gate}

    passed.sort(key=lambda x: -x["_s"])
    fitness = min(1.0, passed[0]["_s"] / 20.0)
    return {"pass": True, "why": "%s 门 %d 处" % (gate, len(passed)),
            "cands": passed, "fitness": fitness, "organ": organ, "gate": gate}


R.policy(rank=10, desc="代码答案 ≥3 处走代码，否则走表（启发式，见研究文档 §e12）")
def _quality(got, k=3):
    if not got or not got.get("cands"):
        return 0.0
    rows = got["cands"][:k]
    def _sc(r):
        return r.get("score", r.get("_s", 0.0))
    return sum(min(1.0, max(0.0, (_sc(r) - 8.0) / 12.0)) for r in rows) / len(rows)


def goal_sig(goal):
    a, b = goal.get("from"), goal.get("to")
    if not a or not b:
        return ""
    if b * 2 in (a, a - 1):
        r = "half"
    elif a * 2 == b:
        r = "double"
    else:
        r = "other"
    q = "q25" if a % 25 == 0 else ("q2" if a % 2 == 0 else "q1")
    return "%s|%s" % (r, q)


def run(exe, goal, rounds=None, cache="var/map_hunt.pkl", fresh=True, sweep=True, seed=None,
        tree_=None):
    if rounds is None:
        rounds = rules.get("rounds", 6)
    if seed is None:
        seed = rules.get("seed", 20261017)
    m = M.build(exe, cache=cache)
    gseed = (seed ^ (zlib.crc32(json.dumps(goal, sort_keys=True).encode()) & 0xFFFFFFFF)) & 0x7FFFFFFF
    g = GedaCore(gene_len=60, seed=gseed)
    if not fresh:
        g.load("var/geda_state.json")

    seen = {}

    if tree_ is None:
        tree_ = TR.SimpleTree(TR.class_features(goal),
                              max_depth=rules.get("tree.max_depth", 3),
                              min_samples=rules.get("tree.min_samples", 8))
        tree_.samples_list = []
    state = {"best": None, "tree": tree_}

    def _take(organ, gate, window):
        key = (organ, gate, window)
        if key in seen:
            return seen[key]
        r = evaluate(m, goal, organ, gate, window=window)
        seen[key] = r
        g.record(r["fitness"], action={"organ": organ, "gate": gate, "window": window},
                 why=r["why"])
        return r

    def _collect(gate, window, via):
        pooled, fitness = [], 0.0
        for organ in ORGANS_ORDER:
            r = _take(organ, gate, window)
            if r["pass"]:
                pooled.extend(r["cands"])
                fitness = max(fitness, r["fitness"])
        if not pooled:
            return None
        uniq = {}
        for c in pooled:
            uniq.setdefault(c.get("fo_imm", c["fo"]), c)
        uniq = prune_for_gate(gate, uniq)
        cands = sorted(uniq.values(), key=lambda x: -x["_s"])
        return {"fit": round(fitness, 3), "gate": gate, "window": window,
                "radius": window, "cands": _shape(cands), "via": via,
                "why": "%s 门 %d 处" % (gate, len(cands))}

    answers = {}
    state["best"] = None
    history = []

    def ph_recon(tk, **_):
        t0 = len(seen)
        fs = M.funcs(m)
        tabs = __import__("record_table").tables(m)
        return {"recon": {"funcs": len(fs), "tables": len(tabs),
                          "cached": t0 * 0}}

    def ph_enum(tk, **_):
        if not sweep:
            return {}
        for gate in GATES_ORDER:
            got = _collect(gate, 48, "冷启动")
            if got:
                answers[gate] = got
        return {"answers": sorted(answers)}

    def ph_rank(tk, **_):
        if state["tree"] is not None:
            samples = []
            for cls in ("record", "arm"):
                if answers.get(cls):
                    samples.append((_class_state(cls, answers[cls], goal), _selfcheck(cls, answers[cls])))
            state["tree"].fit(state["tree"].samples_list + samples)
            state["tree"].samples_list = state["tree"].samples_list + samples
        state["best"] = _pick_class(answers, tree_=state["tree"], goal=goal)
        b = state["best"]
        return {"rank": {"gate": b["gate"] if b else None,
                         "n": len(b["cands"]) if b else 0}}

    def ph_refine(tk, **_):
        best = state["best"]
        techs = []
        for gname in GATES_ORDER:
            if gname == "record":
                techs.append("record@0")
            else:
                techs.extend("%s@%d" % (gname, w) for w in WINDOWS)
        for t in techs:
            g.register_tech(t)
        sig = goal_sig(goal)
        for _ in range(max(0, rounds)):
            seg = g.get_gene_segment(6)
            tech = g.pick_surface(techs, rng=tk.rng)
            gate, wtxt = tech.split("@")
            window = int(wtxt)
            got = _collect(gate, window, "GEDA")
            history.append({"gene": seg, "tech": tech, "gate": gate,
                            "window": window, "hit": bool(got),
                            "w": g.tech_weight(tech)})
            k = rules.get("geda.reward_top_k", 3)
            if got and best is not None and gate == best["gate"]                     and len(got["cands"]) > len(best["cands"]):
                state["best"] = got
                best = got
                reward = rules.get("geda.reward_hit_new", 1.0)
            elif got:
                reward = max(0.1, _quality(got, k))
            else:
                reward = rules.get("geda.reward_miss", -0.5)
            g.update_surface(tech, reward, bool(got), sig=sig)
        return {"refine": {"rounds": len(history)}}

    tk = T.Tick(seed=gseed)
    tk.phase("recon", ph_recon).phase("enum", ph_enum)       .phase("rank", ph_rank).phase("refine", ph_refine)
    data = tk.run()

    if not fresh:
        g.save("var/geda_state.json")

    best = state["best"]
    out = {"goal": goal, "gene": g.snapshot(), "history": history,
           "tick": tk.serialize(), "phases": data}
    if best is None:
        reasons = sorted({r["why"] for r in seen.values() if not r["pass"]})
        out.update({"pass": False, "best": None, "reason": reasons[:6]})
        return out
    out.update({"pass": True, "best": best})
    return out


if __name__ == "__main__":
    exe = sys.argv[1]
    goal = json.loads(sys.argv[2])
    r = run(exe, goal, rounds=int(sys.argv[3]) if len(sys.argv) > 3 else 6)
    print("目标 %s：%s → %s  （宽度 %s）"
          % (goal.get("name"), goal["from"], goal.get("to"), goal.get("width", 1)))
    if not r["pass"]:
        print("拒绝：")
        for w in r["reason"]:
            print("   ·", w)
        sys.exit(0)
    b = r["best"]
    print("判据 %s  窗口 %d  适应度 %.2f  候选 %d 条  （%s）"
          % (b["gate"], b["window"], b["fit"], len(b["cands"]), b["via"]))
    for c in b["cands"][:20]:
        ev = c["evidence"]
        tag = ""
        if ev.get("gate") == "arm":
            tag = "分档%s 同目的地=%s" % (ev.get("switch"), ev.get("same_dest"))
        elif ev.get("gate") == "table":
            tag = "步长%d 同值%d份 字段实%d 基址引用=%s" % (
                ev.get("stride", 0), ev.get("copies", 0), ev.get("solid", 0),
                ev.get("base_ref"))
        print("   %-10s fo=%-8s 分 %5.1f  %-44s %s"
              % (c["va"], c["fo"], c.get("score", c.get("_s", 0)), c["text"], tag))
