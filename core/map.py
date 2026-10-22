# -*- coding: utf-8 -*-
"""PE parser plus disassembler: builds instruction, constant and field indexes."""
from __future__ import annotations

import os
import pickle
import struct

import capstone


def load_pe(path):
    data = open(path, "rb").read()
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe_off:pe_off + 4] == b"PE\0\0", "不是 PE"
    machine = struct.unpack_from("<H", data, pe_off + 4)[0]     # 0x14c=i386 0x8664=x64
    nsec = struct.unpack_from("<H", data, pe_off + 6)[0]
    opt = pe_off + 24
    magic = struct.unpack_from("<H", data, opt)[0]              # 0x10b=PE32 0x20b=PE32+
    if magic == 0x20B:
        base = struct.unpack_from("<Q", data, opt + 24)[0]
    else:
        base = struct.unpack_from("<I", data, opt + 28)[0]
    sec = opt + struct.unpack_from("<H", data, pe_off + 20)[0]
    secs = {}
    for i in range(nsec):
        s = sec + i * 40
        name = data[s:s + 8].rstrip(b"\0").decode("latin1")
        vsize, va, rsize, roff = struct.unpack_from("<IIII", data, s + 8)
        secs[name] = {"va": base + va, "vsize": vsize,
                      "roff": roff, "rsize": rsize}
    return data, base, secs


_MEM = {}


def _md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(path, cache="map.pkl"):
    key = (os.path.abspath(path), cache)
    if key in _MEM:
        return _MEM[key]
    digest = _md5(path)
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            m = pickle.load(f)
        if (m.get("src") == path and m.get("size") == os.path.getsize(path)
                and m.get("md5") in (None, digest)):
            m["md5"] = digest
            _MEM[key] = m
            return m

    data, base, secs = load_pe(path)
    t = secs.get(".text") or secs[[k for k in secs if k.startswith(".text")][0]]
    machine = struct.unpack_from("<H", data, struct.unpack_from("<I", data, 0x3C)[0] + 4)[0]
    mode = capstone.CS_MODE_64 if machine == 0x8664 else capstone.CS_MODE_32
    md = capstone.Cs(capstone.CS_ARCH_X86, mode)
    md.detail = True

    insns, consts, fields = [], [], []
    va0, off0, size = t["va"], t["roff"], t["rsize"]

    off = 0
    while off < size:
        got = list(md.disasm(data[off0 + off: off0 + off + 16], va0 + off, count=1))
        if not got:
            off += 1
            continue
        ins = got[0]
        fo = off0 + off
        insns.append((ins.address, ins.mnemonic, ins.op_str, ins.size, fo))
        ops = ins.operands
        for k, o in enumerate(ops):
            if o.type == 2:
                imm = o.imm & 0xFFFFFFFF
                tail = data[fo:fo + ins.size]
                fo_imm, w = fo, 1
                for cand_w in (4, 2, 1):
                    if (len(tail) >= cand_w and
                            int.from_bytes(tail[-cand_w:], "little") ==
                            (imm & ((1 << (8 * cand_w)) - 1))):
                        fo_imm, w = fo + ins.size - cand_w, cand_w
                        break
                consts.append({"va": ins.address, "imm": imm,
                               "idx": k, "nops": len(ops),
                               "mn": ins.mnemonic,
                               "text": "%s %s" % (ins.mnemonic, ins.op_str),
                               "fo": fo, "fo_imm": fo_imm, "w": w,
                               "size": ins.size})
            elif o.type == 3:
                b = md.reg_name(o.mem.base) if o.mem.base else ""
                fields.append({"va": ins.address, "base": b,
                               "disp": o.mem.disp & 0xFFFFFFFF,
                               "mn": ins.mnemonic,
                               "text": "%s %s" % (ins.mnemonic, ins.op_str),
                               "w": (k == 0 and ins.mnemonic in
                                     ("mov", "add", "sub", "inc", "dec", "or", "and", "xor")),
                               "fo": fo, "size": ins.size})
        off += ins.size

    m = {"src": path, "size": os.path.getsize(path), "md5": digest,
         "base": base, "_raw": data,
         "sections": secs, "insns": insns, "consts": consts, "fields": fields,
         "machine": machine, "bits": 64 if machine == 0x8664 else 32}
    for k in [k for k in m if k.startswith("_") and k != "_raw"]:
        m.pop(k, None)
    _parent = os.path.dirname(os.path.abspath(cache))
    if _parent:
        os.makedirs(_parent, exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump(m, f)
    _MEM[key] = m
    return m


def funcs(m):
    fs = m.get("_funcs")
    if fs is not None:
        return fs
    d = bytes(m["_raw"])
    t = m["sections"][".text"]
    lo, hi = t["roff"], t["roff"] + t["rsize"]
    starts, i = [], lo
    while i < hi:
        if d[i] != 0xCC:
            i += 1
            continue
        j = i
        while j < hi and d[j] == 0xCC:
            j += 1
        if j - i >= 2 and j + 3 <= hi:
            b = d[j:j + 3]
            if (b[0] == 0x55 or b[0] in (0x53, 0x56, 0x57)
                    or b[:2] == bytes([0x83, 0xEC]) or b[:2] == bytes([0x81, 0xEC])
                    or b[:2] == bytes([0x8B, 0xFF])):
                starts.append(j)
        i = j
    fs = list(zip(starts, starts[1:]))
    m["_funcs"] = fs
    return fs


if __name__ == "__main__":
    import sys
    p = sys.argv[1]
    m = build(p)
    print("指令 %d 条 | 立即数 %d 个 | 字段访问 %d 处" %
          (len(m["insns"]), len(m["consts"]), len(m["fields"])))
