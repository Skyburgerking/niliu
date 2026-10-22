# -*- coding: utf-8 -*-
"""Probes the binary (toolchain, instruction shapes) and selects matching presets."""
from __future__ import annotations

import json
import os
import re
import struct
from collections import Counter

import rules

PRESET_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "rules", "presets.json")


def _presets():
    try:
        with open(PRESET_PATH, encoding="utf-8") as f:
            return json.load(f).get("presets", [])
    except Exception:
        return []


def _pe_head(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        return None
    machine, nsec = struct.unpack_from("<HH", d, pe + 4)
    tstamp = struct.unpack_from("<I", d, pe + 8)[0]
    opt_size = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    linker = struct.unpack_from("<BB", d, opt + 2)
    return {"machine": machine, "magic": magic, "nsec": nsec, "linker": linker,
            "tstamp": tstamp, "opt": opt, "pe_off": pe,
            "bits": 64 if machine == 0x8664 else 32}


def _rich(d, h):
    rich = d.find(b"Rich", h["pe_off"] - 0x200, h["pe_off"])
    if rich < 0:
        return None
    key = struct.unpack_from("<I", d, rich + 4)[0]
    dans = d.rfind(b"DanS", 0, rich)
    if dans < 0:
        return None
    out = Counter()
    p = dans
    while p + 8 <= rich:
        comp = struct.unpack_from("<I", d, p)[0] ^ key
        cnt = struct.unpack_from("<I", d, p + 4)[0] ^ key
        if comp != 0x536E6144:
            out[(comp >> 16, comp & 0xFFFF)] += cnt
        p += 8
    return out or None


def _imports(d, h):
    opt = h.get("opt")
    if opt is None:
        return []
    dd = opt + (112 if h.get("magic") == 0x20B else 96)
    try:
        rva, size = struct.unpack_from("<II", d, dd + 8)
    except Exception:
        return []
    if not rva or not size:
        return []
    secs = []
    pe = h["pe_off"]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt_size = struct.unpack_from("<H", d, pe + 20)[0]
    base_sec = opt + opt_size
    for i in range(nsec):
        p = base_sec + i * 40
        vsize, va, rsize, roff = struct.unpack_from("<IIII", d, p + 8)
        secs.append((va, max(vsize, rsize), roff))

    def to_off(v):
        for va, vs, roff in secs:
            if va <= v < va + vs:
                return roff + (v - va)
        return None

    o = to_off(rva)
    out = []
    while o and o + 20 <= len(d):
        nrva = struct.unpack_from("<I", d, o + 12)[0]
        if not nrva:
            break
        q = to_off(nrva)
        if q is None:
            break
        end = d.find(bytes([0]), q)
        out.append(d[q:end].decode("latin1", "replace"))
        o += 20
    return out


def _strings(d, needles, limit=3):
    hit = []
    low = d.lower()
    for n in needles:
        i = low.find(n.lower().encode())
        if i >= 0:
            hit.append(n)
    return hit[:limit]


def probe(m, path=None):
    d = bytes(m["_raw"])
    h = _pe_head(d) or {"bits": m.get("bits", 32), "machine": m.get("machine", 0)}
    ins = m["insns"]
    mn = Counter(i[1] for i in ins)
    cmp_imm = sum(1 for i in ins if i[1] == "cmp" and re.search(r", (0x[0-9a-f]+|\d+)$", i[2]))
    jmp_reg = sum(1 for i in ins if i[1] == "jmp" and re.match(r"^(e|r)[a-z]{2}$", i[2]))
    scaled = sum(1 for i in ins if re.search(r"\* ?[248]", i[2]))
    field_w = sum(1 for i in ins if i[1] == "mov" and
                  re.match(r"^(dword|qword|word|byte) ptr \[", i[2]) and "," in i[2])
    float_ops = sum(1 for i in ins if i[1] in ("movsd", "movss", "fld", "fstp", "addsd", "mulsd"))
    imul_imm = sum(1 for i in ins if i[1] == "imul" and re.search(r", (0x[0-9a-f]+|\d+)$", i[2]))
    jt = 0
    for k, i in enumerate(ins):
        if "*4" in i[2] and i[1] in ("mov", "movsxd", "lea"):
            for j in range(k + 1, min(len(ins), k + 6)):
                if ins[j][1] == "jmp" and re.match(r"^(e|r)[a-z]{2}$", ins[j][2]):
                    jt += 1
                    break
    tables = 0
    try:
        import record_table as RT
        tables = len(RT.tables(m))
    except Exception:
        pass
    imports = _imports(d, h)
    toolchain = "未知"
    rich = _rich(d, h)
    if rich:
        top = max(rich.items(), key=lambda kv: kv[1])[0]
        toolchain = "MSVC (build %d)" % top[0]
    elif any("cygwin" in x.lower() for x in imports):
        toolchain = "Cygwin gcc"
    elif any("msvcrt" in x.lower() or "vcruntime" in x.lower() for x in imports):
        toolchain = "mingw / MSVC（无 Rich：可能被抹）"
    elif "KERNEL32.dll" in imports:
        toolchain = "原生 Win32（无 Rich：可能被抹）"
    out = {
        "toolchain": toolchain,
        "arch": "%d-bit x86" % h.get("bits", 32),
        "bits": h.get("bits", 32),
        "linker": "%d.%d" % tuple(h.get("linker", (0, 0))),
        "timestamp": h.get("tstamp", 0),
        "compiler": "MSVC" if _rich(d, h) else ("未知（无 Rich 头：被抹过或非 MSVC）"),
        "rich": dict(("%d/%d" % k, v) for k, v in (_rich(d, h) or {}).items()),
        "n_insns": len(ins),
        "cmp_imm": cmp_imm, "jmp_reg": jmp_reg, "jt": jt, "scaled": scaled,
        "field_w": field_w, "float_ops": float_ops, "tables": tables,
        "imul_imm": imul_imm,
        "top_mn": dict(mn.most_common(10)),
        "strings": _strings(d, ["il2cpp", "global-metadata", "mscoree.dll",
                                "mono_", "UnityPlayer", "dnfile", "Assembly-CSharp"]),
        "imports": imports,
    }
    return out


def _hit(p, pr):
    det = p.get("detect") or {}
    field = det.get("field")
    if field == "machine":
        return any(x in str(pr.get("arch", "")) for x in (det.get("match") or []))
    if field == "imports":
        imps = [x.lower() for x in pr.get("imports", [])]
        return any(any(m.lower() in i for i in imps) for m in (det.get("match") or []))
    if field == "strings":
        return bool(set(x.lower() for x in pr.get("strings", [])) &
                    set(x.lower() for x in (det.get("match") or [])))
    val = pr.get(field)
    if val is None:
        return False
    if val >= det.get("min", 1):
        return True
    fb = det.get("fallback")
    if fb and pr.get(fb.get("field"), 0) >= fb.get("min", 1):
        return True
    return False


def pick(pr):
    got = []
    for p in _presets():
        if _hit(p, pr):
            got.append({"id": p["id"], "名字": p.get("名字", p["id"]),
                        "status": p.get("status", "todo"),
                        "response": p.get("response", {}),
                        "缺口": p.get("缺口", ""), "实测": p.get("实测", "")})
    ok = [g for g in got if g["status"] == "ok"]
    todo = [g for g in got if g["status"] != "ok"]
    return {"matched": got, "ready": ok, "gaps": todo,
            "plan": [g["response"].get("gate") or g["response"].get("organ")
                     for g in ok]}


def run(m):
    pr = probe(m)
    sel = pick(pr)
    return {"probe": pr, "presets": sel}


def describe(res):
    pr, sel = res["probe"], res["presets"]
    rows = ["摸底：%s  %s  linker %s  时间戳 %d  指令 %d  导入 %d 个 DLL" %
            (pr["arch"], pr.get("toolchain", pr["compiler"]), pr["linker"],
             pr["timestamp"], pr["n_insns"], len(pr.get("imports") or [])),
            "形态：cmp链 %d | 跳表 %d | jmp reg %d | 变址 %d | 字段写 %d | 浮点 %d | 名字表 %d"
            % (pr["cmp_imm"], pr["jt"], pr["jmp_reg"], pr["scaled"],
               pr["field_w"], pr["float_ops"], pr["tables"])]
    if pr.get("imports"):
        rows.append("依赖：%s" % "、".join(pr["imports"][:8]))
    rows.append("能打：%s" % "、".join(g["名字"] for g in sel["ready"]))
    if sel["gaps"]:
        rows.append("缺口：")
        for g in sel["gaps"]:
            rows.append("   · %s —— %s" % (g["名字"], g["缺口"]))
    return "\n".join(rows)


if __name__ == "__main__":
    import sys

    import map as M
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "测试/PvZ_原件.exe.newniliu_bak_20261017_202317"
    m = M.build(path, cache="var/map_profile.pkl")
    print(describe(run(m)))
