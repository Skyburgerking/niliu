# -*- coding: utf-8 -*-
"""Replays a known byte list with original-file check, read-back and archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def load_facts(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, dict) and "ops" in d:
        return d["ops"]
    ops = []
    if isinstance(d, dict):
        for grp in d.values():
            ops.extend(grp.get("ops", grp) if isinstance(grp, dict) else grp)
    return ops


def record(path, exe, backup, ops, ok, note=""):
    d = os.path.join(os.path.dirname(os.path.abspath(path)), "var", "archives")
    os.makedirs(d, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(d, "%s_replay.json" % stamp)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"exe": exe, "backup": backup, "ok": ok, "note": note,
                   "n": len(ops), "ops": ops}, f, ensure_ascii=False, indent=1)
    return out


def replay(exe, facts, dry=False, allow_already=False):
    ops = load_facts(facts)
    raw = open(exe, "rb").read()
    plan, done, skip, bad = [], 0, 0, []

    for o in ops:
        off, orig, new = o["file_off"], bytes.fromhex(o["orig"]), bytes.fromhex(o["new"])
        cur = raw[off:off + len(orig)]
        if cur == orig:
            plan.append(o)
        elif cur == new and allow_already:
            skip += 1
        elif cur == new:
            bad.append({"file_off": off, "why": "已经是新值（可能已落过盘），加 --allow-already",
                        "cur": cur.hex()})
        else:
            bad.append({"file_off": off, "why": "原件对不上", "cur": cur.hex(),
                        "expect": orig.hex()})

    if bad:
        return {"ok": False, "refused": True, "bad": bad[:8],
                "note": "有 %d 处的原件对不上，一个字节都不写" % len(bad)}

    print("待落 %d 处，已是新值 %d 处" % (len(plan), skip))
    if dry:
        for o in plan[:10]:
            print("  0x%06x %s -> %s" % (o["file_off"], o["orig"], o["new"]))
        return {"ok": True, "dry": True, "n": len(plan)}

    backup = exe + ".newniliu_bak_%s" % time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(exe, backup)
    data = bytearray(raw)
    for o in plan:
        off = o["file_off"]
        nb = bytes.fromhex(o["new"])
        data[off:off + len(nb)] = nb
        done += 1
    with open(exe, "wb") as f:
        f.write(data)

    chk = open(exe, "rb").read()
    wrong = [o for o in plan if chk[o["file_off"]:o["file_off"] + len(o["new"]) // 2].hex() != o["new"]]
    ok = not wrong
    if not ok:
        shutil.copy2(backup, exe)
        return {"ok": False, "rolled_back": True, "wrong": len(wrong)}

    arc = record(facts, exe, backup, plan, ok)
    return {"ok": True, "applied": done, "skipped": skip,
            "md5": md5(exe), "backup": os.path.basename(backup),
            "archive": arc, "readback": "ok"}


def restore(archive):
    with open(archive, encoding="utf-8") as f:
        a = json.load(f)
    shutil.copy2(a["backup"], a["exe"])
    return {"ok": True, "restored_from": os.path.basename(a["backup"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--facts", default="facts/pvz_current.json")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--allow-already", action="store_true")
    ap.add_argument("--restore", default="")
    a = ap.parse_args()
    if a.restore:
        r = restore(a.restore)
    else:
        r = replay(a.exe, a.facts, a.dry, a.allow_already)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
