# -*- coding: utf-8 -*-
"""Niliu engine module."""
from __future__ import annotations

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "core"))

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
sys.path.insert(0, CORE)
os.chdir(ROOT)

ROWS = []


def record(name, ok, detail=""):
    ROWS.append((name, bool(ok), detail))
    return ok


REQUIRED = ["record.min_gcd", "record.table_strides", "arm.gate_min",
            "class.code_min_sites", "geda.prior", "geda.stall_threshold",
            "windows", "rounds", "seed", "guards.big_file_lines"]


def g1_rules():
    import rules
    r = rules.all()
    missing = []
    for k in REQUIRED:
        if rules.get(k) is None:
            missing.append(k)
    ok = os.path.exists(os.path.join(ROOT, "rules", "rules.json")) and not missing
    record("守卫1 规则完整", ok, "缺: %s" % "、".join(missing) if missing else "")
    return r


def g2_organs():
    import registry as R
    import hunt
    names = list(R.ORGANS)
    bad = []
    for n in names:
        spec = R.ORGANS[n]
        if not callable(spec.get("fn")) or not spec.get("gates"):
            bad.append(n)
    min_organs = 5
    ok = len(names) >= min_organs and not bad
    record("守卫2 器官自注册", ok, "%d 个：%s" % (len(names), "、".join(names)))
    return names


def g3_no_hardcode():
    hits = []
    for fn in (os.path.join("core", "hunt.py"), "niliu.py"):
        src = open(os.path.join(ROOT, fn), encoding="utf-8").read()
        for m in re.finditer(r'if\s+organ\s*==\s*["\']', src):
            hits.append("%s: 器官名硬编码" % fn)
        for m in re.finditer(r'if\s+gate\s*==\s*"(table|pair)"', src):
            hits.append("%s: 判据名硬编码 %s" % (fn, m.group(1)))
    record("守卫3 主流程无器官名单", not hits, "；".join(hits[:3]))
    return not hits


def g4_size():
    import rules
    limit = rules.get("guards.big_file_lines", 700)
    big = []
    for d in (CORE, os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(d, fn)
            n = len(open(p, encoding="utf-8").readlines())
            if n > limit:
                big.append("%s %d 行" % (fn, n))
    record("守卫4 单文件≤%d行" % limit, not big, "；".join(big))
    return not big


def g5_rules_used():
    import rules
    src = ""
    for fn in ("hunt.py", "record_table.py", "geda.py", "addr.py", "exam.py",
               "klass.py", "tree.py", "tick.py"):
        src += open(os.path.join(CORE, fn), encoding="utf-8").read()
    unused = []
    for key in ("record.min_gcd", "record.min_ratio", "record.min_lift",
                "record.strong_votes", "record.max_sites", "record.filler_run",
                "arm.gate_min", "arm.acc_pure_bonus", "arm.acc_derived_penalty",
                "class.code_min_sites", "geda.prior", "geda.step_max",
                "geda.stall_threshold", "geda.doubt_threshold",
                "geda.hot_reward", "geda.exp_reward"):
        if ('"%s"' % key) not in src:
            unused.append(key)
    record("守卫5 规则真被读", not unused, "规则文件里有、代码没读：%s" % "、".join(unused)
           if unused else "%d 条抽查全在用" % 16)
    return not unused


def g6_gate_contract():
    import inspect

    import hunt as H
    bad = []
    for name in H.GATES_ORDER:
        fn = H.gate_fn(name) if hasattr(H, "gate_fn") else H.GATES.get(name)
        if name == "record":
            continue
        if fn is None:
            bad.append("%s 没实现" % name)
            continue
        src = inspect.getsource(fn)
        if "return None" not in src or "return score, ev" not in src:
            bad.append("%s 契约不符（要 return None / return score, ev）" % name)
    record("守卫6 判据契约", not bad, "；".join(bad))
    return not bad


def g7_outputs():
    hits = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "var", "结果")]
        for fn in files:
            if fn.endswith((".pyc",)):
                continue
            p = os.path.join(root, fn)
            if "cygwin64" in os.path.abspath(p):
                hits.append(p)
    record("守卫7 产物不落 cygwin64", not hits, "；".join(hits[:2]))
    return not hits


def g8_land_readback():
    src = open(os.path.join(ROOT, "niliu.py"), encoding="utf-8").read()
    has_back = "back = open(self.path" in src or "back = open(" in src
    has_field = '"readback"' in src
    has_guard = "不是这次 ask/step 出来的站点" in src
    ok = has_back and has_field and has_guard
    record("守卫8 land 独立回读", ok,
           "回读=%s 字段=%s 站点校验=%s" % (has_back, has_field, has_guard))
    return ok


def g9_smoke():
    import os as _os
    exe = "测试/PvZ_原件.exe.newniliu_bak_20261017_202317"
    if not _os.path.exists(exe):
        record("守卫9 器官冒烟", True, "跳过（没有靶子 exe）")
        return True
    import hunt as H
    import map as M
    m = M.build(exe, cache="var/map_guard.pkl")
    goal = {"from": 150, "to": 75, "width": 1}
    errs = []
    for organ in H.ORGANS_ORDER:
        for gate in H.GATES_ORDER:
            try:
                ev = H.evaluate(m, goal, organ, gate, window=48)
                if not isinstance(ev, dict) or "pass" not in ev:
                    errs.append("%s×%s 返回形状不对" % (organ, gate))
            except Exception as e:
                errs.append("%s×%s: %r" % (organ, gate, e))
    record("守卫9 器官冒烟（%d×%d）" % (len(H.ORGANS_ORDER), len(H.GATES_ORDER)),
           not errs, "；".join(errs[:2]) if errs else "全部跑通")
    return not errs


def g10_meta(quick=False):
    ok = True
    detail = []

    def _try(name, make_bad, guard, clean):
        nonlocal ok
        bad_green = None
        before = len(ROWS)
        try:
            make_bad()
            guard()
            bad_green = ROWS[before][1]
        except Exception as e:
            detail.append("%s 抛异常：%r" % (name, e))
            ok = False
        finally:
            del ROWS[before:]
            try:
                clean()
            except Exception:
                pass
        if bad_green is None:
            return
        if bad_green:
            ok = False
            detail.append("%s 验不出红" % name)
        else:
            detail.append("%s 能红 ✓" % name)

    bad_file = os.path.join(ROOT, "tools", "_mtest_big.py")

    def _mk_big():
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("\n".join(["# pad"] * 720) + "\n")

    _try("守卫4", _mk_big, g4_size,
         lambda: os.path.exists(bad_file) and os.remove(bad_file))

    import registry as R

    def _mk_fake():
        R.ORGANS["_mtest_fake"] = {"fn": None, "gates": [], "desc": "坏的"}

    _try("守卫2", _mk_fake, g2_organs, lambda: R.ORGANS.pop("_mtest_fake", None))

    import hunt as H

    def _mk_bad_gate():
        def _bad_gate(m, c, goal, window=0):
            return "nope"
        import registry as R
        R.GATES["_mtest_bad"] = {"fn": _bad_gate, "rank": 0,
                                 "desc": "", "name": "_mtest_bad"}
        H.GATES_ORDER.append("_mtest_bad")

    def _clean_bad_gate():
        import registry as R
        R.GATES.pop("_mtest_bad", None)
        if "_mtest_bad" in H.GATES_ORDER:
            H.GATES_ORDER.remove("_mtest_bad")

    _try("守卫6", _mk_bad_gate, g6_gate_contract, _clean_bad_gate)

    record("守卫10 元测试（守卫能变红）", ok, "、".join(detail))
    return ok


def g11_generality():
    import rules
    import subprocess
    want = int(rules.get("generality.min_hits", 4))
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "tests/generality.py"],
                           capture_output=True, text=True, timeout=600,
                           encoding="utf-8", errors="replace", env=env)
        tail = (r.stdout or "").strip().splitlines()
        line = [l for l in tail if "命中" in l]
        got = 0
        if line:
            import re as _re
            m = _re.search(r"命中\s*(\d+)", line[-1])
            got = int(m.group(1)) if m else 0
        ok = got >= want
        record("守卫11 通用性靶场", ok, "命中 %d/%s（及格线 %d）"
               % (got, line[-1].split("/")[-1].split("，")[0] if line else "?", want))
        return ok
    except Exception as e:
        record("守卫11 通用性靶场", False, "跑不起来：%r" % e)
        return False


def g12_presets():
    import json
    import profile as PF
    import map as M
    import rules
    want_ready = int(rules.get("presets.min_ready", 4))
    try:
        pres = PF._presets()
    except Exception as e:
        record("守卫12 预设库", False, "读不了规则/预设.json：%r" % e)
        return False
    bad = [p.get("id", "?") for p in pres
           if not p.get("id") or not p.get("detect") or not p.get("response")
           or p.get("status") not in ("ok", "partial", "todo")]
    if bad:
        record("守卫12 预设库", False, "条目不全：%s" % bad[:4])
        return False
    try:
        m = M.build("tests/bin/t64.exe", cache="var/map_guard12.pkl")
        pr = PF.probe(m)
        fields = {p["detect"].get("field") for p in pres}
        got = {k for k in ("cmp_imm", "jt", "jmp_reg", "scaled", "field_w",
                           "float_ops", "tables") if pr.get(k, 0) > 0}
        miss = sorted(got - fields)
        sel = PF.pick(pr)
    except Exception as e:
        record("守卫12 预设库", False, "选预设跑不起来：%r" % e)
        return False
    if miss:
        record("守卫12 预设库", False, "这些形态没有预设：%s" % miss)
        return False
    ok = len(sel["ready"]) >= want_ready
    record("守卫12 预设库", ok, "%d 条预设 / 能打 %d（要求≥%d）/ 缺口 %d"
           % (len(pres), len(sel["ready"]), want_ready, len(sel["gaps"])))
    return ok


def main():
    quick = "--quick" in sys.argv
    g1_rules()
    organs = g2_organs() if not quick else None
    g3_no_hardcode()
    g4_size()
    g5_rules_used()
    g6_gate_contract()
    g7_outputs()
    g8_land_readback()
    if not quick:
        g9_smoke()
    g10_meta(quick)
    if not quick:
        g11_generality()
        g12_presets()

    print("== 新逆流 结构守卫 ==")
    for name, ok, detail in ROWS:
        print("  %s  %-26s %s" % ("✓" if ok else "✗", name, detail))
    red = [r for r in ROWS if not r[1]]
    print("\n%d 条，绿 %d，红 %d" % (len(ROWS), len(ROWS) - len(red), len(red)))
    if red:
        print("**有红的，别往下走。**")
        return 1
    print("全绿。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
