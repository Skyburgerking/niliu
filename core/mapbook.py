# -*- coding: utf-8 -*-
"""Map book: exports and searches sites that were already landed and verified."""
from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ops_of(rec):
    out = []
    for op in rec.get("ops") or []:
        where = op.get("where")
        if where is None:
            continue
        try:
            off = int(str(where), 0)
        except ValueError:
            continue
        out.append({"site": off, "width": op.get("width", 1),
                    "from": op.get("orig_i"), "to": op.get("new_i"),
                    "orig": op.get("orig"), "new": op.get("new")})
    return out


def collect():
    book = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "var", "archives", "*.json"))):
        try:
            rec = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        name = rec.get("id") or os.path.basename(path)[:-5]
        book[name] = {
            "kind": "land",
            "exe": rec.get("path"),
            "md5_before": rec.get("file_md5_before"),
            "md5_after": rec.get("file_md5_after"),
            "backup": rec.get("backup"),
            "ops": _ops_of(rec),
        }

    for path in sorted(glob.glob(os.path.join(ROOT, "facts", "*.json"))):
        try:
            facts = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(facts, dict):
            continue
        for key, val in facts.items():
            if not isinstance(val, dict) or "ops" not in val:
                continue
            ops = []
            for op in val["ops"]:
                off = op.get("file_off", op.get("site"))
                if off is None:
                    continue
                ops.append({"site": int(off), "width": len(op.get("orig", "")) // 2 or 1,
                            "from": None, "to": None,
                            "orig": op.get("orig"), "new": op.get("new")})
            book["facts:" + key] = {"kind": "facts", "exe": None,
                                    "md5_before": None, "md5_after": None,
                                    "backup": None, "ops": ops}
    return book


def search(book, q):
    q = (q or "").strip().lower()
    if not q:
        return book
    return {k: v for k, v in book.items() if q in k.lower()}


def to_md(book, title="逆流地图"):
    lines = ["# %s" % title, "",
             "> 已落盘验证过的站点。`site` 是**文件偏移**，`width` 是改几个字节。", ""]
    for name in sorted(book):
        e = book[name]
        lines.append("## %s" % name)
        if e.get("md5_before"):
            lines.append("- 改前 md5 `%s` → 改后 `%s`" % (e["md5_before"][:12], (e["md5_after"] or "")[:12]))
        if e.get("backup"):
            lines.append("- 备份 `%s`" % os.path.basename(e["backup"]))
        for op in e["ops"][:40]:
            lines.append("- `%#x` w=%s  %s → %s" % (op["site"], op["width"],
                                                    op.get("orig"), op.get("new")))
        if len(e["ops"]) > 40:
            lines.append("- …… 共 %d 处" % len(e["ops"]))
        lines.append("")
    return "\n".join(lines)


def export(out_base):
    book = collect()
    d = os.path.dirname(out_base)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out_base + ".json", "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=1)
    with open(out_base + ".md", "w", encoding="utf-8") as f:
        f.write(to_md(book, os.path.basename(out_base)))
    total = sum(len(v["ops"]) for v in book.values())
    return {"ok": True, "targets": len(book), "sites": total,
            "json": out_base + ".json", "md": out_base + ".md"}
