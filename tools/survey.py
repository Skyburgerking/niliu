# -*- coding: utf-8 -*-
"""Niliu engine module."""
from __future__ import annotations

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "core"))

import os
import re
import struct
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

DEFAULT = "测试/PvZ_原件.exe.newniliu_bak_20261017_202317"


def pe_header(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[pe:pe + 4] == b"PE\0\0", "不是 PE"
    machine, nsec = struct.unpack_from("<HH", d, pe + 4)
    tstamp = struct.unpack_from("<I", d, pe + 8)[0]
    opt_size = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    linker = struct.unpack_from("<BB", d, opt + 2)          # Major/MinorLinkerVersion
    subsystem = struct.unpack_from("<H", d, opt + 68)[0]
    if magic == 0x20B:
        base = struct.unpack_from("<Q", d, opt + 24)[0]
        entry = struct.unpack_from("<I", d, opt + 16)[0]
    else:
        base = struct.unpack_from("<I", d, opt + 28)[0]
        entry = struct.unpack_from("<I", d, opt + 16)[0]
    sec = opt + opt_size
    secs = []
    for i in range(nsec):
        s = sec + i * 40
        name = d[s:s + 8].rstrip(b"\0").decode("latin1")
        vsize, va, rsize, roff = struct.unpack_from("<IIII", d, s + 8)
        chars = struct.unpack_from("<I", d, s + 36)[0]
        secs.append({"name": name, "va": va, "vsize": vsize,
                     "roff": roff, "rsize": rsize, "chars": chars})
    return {"machine": machine, "magic": magic, "nsec": nsec, "linker": linker,
            "tstamp": tstamp, "subsystem": subsystem, "base": base, "entry": entry,
            "secs": secs, "pe_off": pe, "opt": opt}


def rich_header(d, info):
    rich = d.find(b"Rich", info["pe_off"] - 0x200, info["pe_off"])
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
        if comp == 0x536E6144:                              # 'DanS'
            p += 8
            continue
        out[(comp >> 16, comp & 0xFFFF)] += cnt
        p += 8
    return out or None


def pdb_info(d, info):
    opt = info["opt"]
    if info["magic"] == 0x20B:
        dd = opt + 112
    else:
        dd = opt + 96
    rva, size = struct.unpack_from("<II", d, dd + 6 * 8)
    if not rva or not size:
        return None
    for s in info["secs"]:
        if s["va"] <= rva < s["va"] + max(s["vsize"], s["rsize"]):
            o = s["roff"] + (rva - s["va"])
            if d[o:o + 4] == b"RSDS":
                guid = d[o + 4:o + 20].hex()
                age = struct.unpack_from("<I", d, o + 20)[0]
                end = d.find(b"\0", o + 24)
                return {"pdb": d[o + 24:end].decode("latin1", "replace"),
                        "guid": guid, "age": age}
    return None


def imports(d, info):
    opt = info["opt"]
    dd = opt + (112 if info["magic"] == 0x20B else 96)
    rva, size = struct.unpack_from("<II", d, dd + 8)
    if not rva or not size:
        return []
    def to_off(v):
        for s in info["secs"]:
            if s["va"] <= v < s["va"] + max(s["vsize"], s["rsize"]):
                return s["roff"] + (v - s["va"])
        return None
    o = to_off(rva)
    out = []
    while o and o + 20 <= len(d):
        name_rva = struct.unpack_from("<I", d, o + 12)[0]
        if not name_rva:
            break
        p = to_off(name_rva)
        if p is None:
            break
        end = d.find(b"\0", p)
        out.append(d[p:end].decode("latin1", "replace"))
        o += 20
    return out


def idioms(m):
    ins = m["insns"]
    mn = Counter(i[1] for i in ins)
    n = len(ins)

    cmp_imm = [i for i in ins if i[1] == "cmp" and re.search(r", (0x[0-9a-f]+|\d+)$", i[2])]
    lea_rip = [i for i in ins if i[1] == "lea" and "rip" in i[2]]
    jmp_reg = [i for i in ins if i[1] == "jmp" and re.match(r"^(e|r)[a-z]{2}$", i[2])]
    scaled = [i for i in ins if re.search(r"[a-z0-9]+ \* [248]|\*[248]", i[2])]
    jt = []
    for k, i in enumerate(ins):
        if re.search(r"\*4", i[2]) and i[1] in ("mov", "movsxd", "lea"):
            for j in range(k + 1, min(len(ins), k + 6)):
                if ins[j][1] == "jmp" and re.match(r"^(e|r)[a-z]{2}$", ins[j][2]):
                    jt.append(i)
                    break
    field_w = [i for i in ins if i[1] == "mov" and re.match(r"^(dword|qword|word|byte) ptr \[", i[2])]
    floats = [i for i in ins if i[1] in ("movsd", "movss", "fld", "fstp", "addsd", "mulsd")]
    indirect = [i for i in ins if i[1] in ("call", "jmp") and re.match(r"^(e|r)[a-z]{2}$|\[", i[2])]
    return {"n": n, "mn": mn, "cmp_imm": len(cmp_imm), "lea_rip": len(lea_rip),
            "jmp_reg": len(jmp_reg), "scaled": len(scaled), "field_w": len(field_w),
            "float_ops": len(floats), "indirect": len(indirect), "jt": len(jt)}


def main():
    import map as M
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    d = open(path, "rb").read()
    info = pe_header(d)
    print("=" * 70)
    print("   摸底：%s（%d 字节）" % (os.path.basename(path), len(d)))
    print("=" * 70)
    bits = 64 if info["machine"] == 0x8664 else 32
    print("① PE 头")
    print("   位数      : %d 位（machine=0x%x, magic=0x%x）" % (bits, info["machine"], info["magic"]))
    print("   链接器    : %d.%d    子系统: %d" % (info["linker"][0], info["linker"][1], info["subsystem"]))
    print("   时间戳    : %d（%s）" % (info["tstamp"],
                                     __import__("time").strftime("%Y-%m-%d %H:%M", __import__("time").localtime(info["tstamp"]))))
    print("   ImageBase : 0x%x   入口 0x%x" % (info["base"], info["entry"]))
    print("   段        : %s" % "  ".join("%s(0x%x)" % (s["name"], s["rsize"]) for s in info["secs"]))

    rich = rich_header(d, info)
    print("\n② Rich 头（MSVC 工具链版本）")
    if rich:
        for (build, prod), cnt in sorted(rich.items(), key=lambda kv: -kv[1])[:8]:
            print("   build %-6d 产品 %-4d 出现 %d 次" % (build, prod, cnt))
    else:
        print("   没有 Rich 头 → 多半不是 MSVC 编的（gcc/clang/其他）")

    pdb = pdb_info(d, info)
    print("\n③ 调试目录")
    print("   %s" % (("PDB: %s（age %d）" % (pdb["pdb"], pdb["age"])) if pdb else "没有 PDB 信息"))

    imps = imports(d, info)
    print("\n④ 导入表（%d 个 DLL）" % len(imps))
    print("   %s" % "、".join(imps[:12]))

    m = M.build(path, cache="var/map_probe_%s.pkl" % bits)
    idm = idioms(m)
    print("\n⑤ 汇编形状（%d 条指令）" % idm["n"])
    top = "  ".join("%s %d" % (k, v) for k, v in idm["mn"].most_common(14))
    print("   助记符    : %s" % top)
    print("   立即数比较: %-6d  ← 『分档 iff 链』的原料（gate_arm）" % idm["cmp_imm"])
    print("   rip 取址  : %-6d  ← 『跳表/常量引用』的原料" % idm["lea_rip"])
    print("   jmp reg   : %-6d  ← 『跳表分派』的标志" % idm["jmp_reg"])
    print("   变址寻址  : %-6d  ← base + idx*4/8（数组/跳表/结构表）" % idm["scaled"])
    print("   字段写    : %-6d  ← mov [mem], imm（对象初始化/血量）" % idm["field_w"])
    print("   浮点运算  : %-6d  ← movsd/fld/addsd" % idm["float_ops"])
    print("   间接转移  : %-6d" % idm["indirect"])
    print("   跳表分派  : %-6d  ← 变址取表项 + 近处 jmp reg（gate_jt 的原料）" % idm["jt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
