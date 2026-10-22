# -*- coding: utf-8 -*-
"""Niliu engine module."""
from __future__ import annotations

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "core"))

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import hunt as H  # noqa: E402
import map as M  # noqa: E402

BIN = "tests/bin"
WORK = "tests/work"


def build(src="tests/bench/t_target.c"):
    os.makedirs(BIN, exist_ok=True)
    jobs = [("gcc", "t32.exe"), ("x86_64-w64-mingw32-gcc", "t64.exe")]
    out = []
    for cc, name in jobs:
        dst = os.path.join(BIN, name)
        r = subprocess.run([cc, "-O1", "-o", dst, src],
                           capture_output=True, text=True)
        if r.returncode == 0:
            out.append(dst)
        else:
            print("  ! %s 编译失败：%s" % (name, (r.stderr or "").strip()[:120]))
    return out


def run_exe(path):
    r = subprocess.run([path], capture_output=True, text=True, timeout=20)
    try:
        return json.loads(r.stdout.strip().splitlines()[0])
    except Exception:
        return {"_raw": (r.stdout or "")[:80], "_err": (r.stderr or "")[:80]}


def width_of(m, fo):
    raw = bytes(m["_raw"])
    for w in (4, 2, 1):
        if fo + w <= len(raw):
            yield w, int.from_bytes(raw[fo:fo + w], "little")


def patch(src, dst, fo, to, width):
    shutil.copy2(src, dst)
    with open(dst, "r+b") as f:
        f.seek(fo)
        f.write(int(to).to_bytes(width, "little"))
    return dst


CASES = [
    ("表列", 25, 50, {"cost_sum": 275}),
    ("分档", 15, 50, {"case5": 50}),
    ("浮点", 121, 89, {"cd": 25.0}),
]


def main():
    os.makedirs(WORK, exist_ok=True)
    bins = build()
    if not bins:
        print("没有靶子可跑（gcc 不在？）")
        return 1

    rows = []
    for exe in bins:
        bit = 64 if "t64" in exe else 32
        m = M.build(exe, cache=os.path.join(WORK, "map_%d.pkl" % bit))
        base = run_exe(exe)
        print("\n=== %s（%d 位）基线 %s" % (os.path.basename(exe), bit, base))
        for name, a, b, want in CASES:
            r = H.run(exe, {"from": a, "to": b, "width": 1}, rounds=4,
                      cache=os.path.join(WORK, "map_%d.pkl" % bit), fresh=True)
            if not r["pass"]:
                rows.append((bit, name, "无答案", ""))
                print("  ✗ %-4s %d->%d  引擎没给答案（%s）" % (name, a, b,
                                                          (r.get("reason") or [""])[0] if r.get("reason") else ""))
                continue
            got = r["best"]["cands"]
            hit = None
            for c in got:
                fo = int(c["fo"], 16)
                for w, val in width_of(m, fo):
                    if val != a:
                        continue
                    tmp = os.path.join(WORK, "t_%d_%s_%d.exe" % (bit, name, fo))
                    patch(exe, tmp, fo, b, w)
                    after = run_exe(tmp)
                    os.remove(tmp)
                    if all(abs(after.get(k, -999) - v) < 1e-6 for k, v in want.items()):
                        hit = (fo, w, after)
                        break
                if hit:
                    break
            if hit:
                rows.append((bit, name, "命中", "0x%x 宽%d 读数 %s" % (hit[0], hit[1], hit[2])))
                print("  ✓ %-4s %d->%d  站点 0x%x（宽%d）→ 行为对上了：%s"
                      % (name, a, b, hit[0], hit[1], hit[2]))
            else:
                rows.append((bit, name, "未命中", "给了 %d 处都不对" % len(got)))
                print("  ✗ %-4s %d->%d  给了 %d 处，行为都没对上" % (name, a, b, len(got)))

    ok = sum(1 for r in rows if r[2] == "命中")
    print("\n%d 个考点（%d 位 × %d 类），命中 %d" % (len(rows), len({r[0] for r in rows}),
                                                  len(CASES), ok))
    json.dump([{"bits": r[0], "case": r[1], "result": r[2], "detail": r[3]} for r in rows],
              open("结果/通用性.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
