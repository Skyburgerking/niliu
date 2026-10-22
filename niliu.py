# -*- coding: utf-8 -*-
"""Niliu engine module."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

import archive as AR
import hunt as H
import profile as PF
import map as M
from geda import GedaCore

try:
    import live_ops as _LIVE
    _LIVE_OPS = _LIVE.LIVE_OPS
except Exception:                       # noqa: BLE001
    _LIVE = None
    _LIVE_OPS = ()

OPS = ("help", "start", "ask", "step", "state", "techs", "land", "map",
       "near", "refs", "explain", "stop") + tuple(_LIVE_OPS)


if _LIVE:
    _LIVE.attach_live.__doc__ = "把 live_* 挂到引擎上"
ROOT = os.path.dirname(os.path.abspath(__file__))


def _out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _iv(v, default=None):
    if v is None:
        return default
    if isinstance(v, int):
        return v
    s = str(v).strip()
    return int(s, 0)


def _cache_for(path):
    h = hashlib.md5(open(path, "rb").read()).hexdigest()
    key = "%s:%s" % (os.path.basename(path), h[:12])
    d = os.path.join(ROOT, "var")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "map_%s.pkl" % hashlib.md5(key.encode("utf-8")).hexdigest()[:8])


class Engine(object):
    def __init__(self):
        self.m = None
        self.path = None
        self.goal = {}
        self.g = GedaCore(gene_len=60)
        self.seen = set()
        self.iters = 0
        self.t0 = time.time()

    def _guard(self):
        if self.m is None:
            return {"ok": False, "err": "还没 start"}
        return None

    def _goal_from(self, req):
        goal = {}
        for k in ("from", "to", "width"):
            if req.get(k) is not None:
                goal[k] = _iv(req.get(k))
        if goal.get("width") is None:
            goal["width"] = 4 if (goal.get("from") or 0) > 0xFFFF else 1
        if req.get("name"):
            goal["name"] = req["name"]
        return goal

    # ------------------------------------------------------------ op
    def op_help(self, req=None):
        kinds = list(H.GATES_ORDER) + [g for g in H.R.GATES if g not in H.GATES_ORDER]
        return {"ok": True, "ops": list(OPS),
                "gates": kinds, "organs": list(H.ORGANS_ORDER),
                "windows": list(H.WINDOWS),
                "ask_kinds": ["auto"] + kinds,
                "note": ("一行 JSON 进、一行 JSON 出。先 start{exe,from,to}，"
                         "再 ask{kind} 或 step{n}；land 只认 ask 回的 site")}

    def op_start(self, req):
        path = req.get("exe")
        if not path or not os.path.isfile(path):
            return {"ok": False, "err": "exe 不存在：%s" % path}
        t0 = time.time()
        self.path = os.path.abspath(path)
        self.m = M.build(self.path, cache=_cache_for(self.path))
        goal = self._goal_from(req)
        if not goal.get("from"):
            return {"ok": False, "err": "start 要给 from（要找的原值），可选 to/width"}
        self.goal = goal
        self.seen = set()
        self.iters = 0
        self.md5 = self.m.get("md5") or AR.md5_of(self.path)
        arc = AR.load(self.md5, os.path.basename(self.path))
        self.recall = AR.recall(self.md5, goal, os.path.basename(self.path))
        try:
            prof = PF.run(self.m)
        except Exception as e:
            prof = None
            self.log_err = repr(e)
        return {"ok": True, "exe": self.path,
                "archive": {"structure": arc.get("structure") or {},
                            "known_goals": len(arc.get("goals") or {}),
                            "recall": self.recall},
                "size": os.path.getsize(self.path), "base": "0x%x" % self.m["base"],
                "insns": len(self.m["insns"]), "consts": len(self.m["consts"]),
                "fields": len(self.m["fields"]), "goal": self.goal,
                "build_s": round(time.time() - t0, 1),
                "profile": prof.get("probe") if prof else {"err": "摸底失败"},
                "presets": {"ready": [g["名字"] for g in (prof.get("presets") or {}).get("ready", [])],
                            "gaps": [{"名字": g["名字"], "缺口": g["缺口"]}
                                     for g in (prof.get("presets") or {}).get("gaps", [])]}}

    def op_ask(self, req):
        err = self._guard()
        if err:
            return err
        budget = float(req.get("budget_s") or 120)
        goal = dict(self.goal)
        goal.update(self._goal_from(req))
        if not goal.get("from"):
            return {"ok": False, "err": "没给 from（也可以 start 时给）"}
        kind = req.get("kind") or "auto"
        top = int(req.get("top") or 12)
        t0 = time.time()

        if kind == "auto":
            r = H.run(self.path, goal, rounds=0, cache=_cache_for(self.path), fresh=True)
            if not r["pass"]:
                used = time.time() - t0
                return {"ok": False, "err": "没有判据通过", "used_s": round(used, 2),
                        "reasons": r.get("reason")}
            rows = r["best"]["cands"]
            gate, window = r["best"]["gate"], r["best"]["window"]
        else:
            if kind not in H.GATES_ORDER and kind not in H.GATES and kind not in H.R.GATES:
                return {"ok": False, "err": "不认识的 kind：%s" % kind}
            window = int(req.get("window") or 48)
            pooled = {}
            for organ in H.ORGANS_ORDER:
                ev = H.evaluate(self.m, goal, organ, kind, window=window)
                if ev["pass"]:
                    for c in ev["cands"]:
                        pooled.setdefault(c.get("fo_imm", c["fo"]), c)
            pooled = H.prune_for_gate(kind, pooled)
            if not pooled:
                used = time.time() - t0
                return {"ok": False, "err": "%s 判据没有站点" % kind,
                        "used_s": round(used, 2)}
            cands = sorted(pooled.values(), key=lambda x: -x["_s"])
            rows = H._shape(cands)
            gate = kind

        used = time.time() - t0
        if used > budget:
            return {"ok": False, "err": "budget", "used_s": round(used, 2)}
        for row in rows:
            self.seen.add(row["fo"])
        widths = {d["w"] for d in self.m["consts"]
                  if d["fo_imm"] == int(rows[0]["fo"], 16)} if rows else set()
        rec = self.recall if (self.recall and self.recall.get("goal")
                              == "%s->%s" % (goal.get("from"), goal.get("to"))) else None
        return {"ok": True, "gate": gate, "window": window, "n": len(rows),
                "used_s": round(used, 2),
                "recall": rec,
                "site_width": (min(widths) if widths else goal["width"]),
                "rows": [{"site": row["fo"], "va": row["va"], "text": row["text"],
                          "score": row.get("score", row.get("_s", 0)),
                          "evidence": row.get("evidence", row.get("_ev", {}))}
                         for row in rows[:top]]}

    def op_step(self, req):
        err = self._guard()
        if err:
            return err
        n = int(req.get("n") or 1)
        log = []
        for _ in range(max(1, min(n, 20))):
            seg = self.g.get_gene_segment(6)
            techs = []
            for gname in H.GATES_ORDER:
                if gname in H.WINDOWLESS:
                    techs.append("%s@0" % gname)
                else:
                    techs.extend("%s@%d" % (gname, w) for w in H.WINDOWS)
            for t in techs:
                self.g.register_tech(t)
            tech = self.g.pick_surface(techs)
            gate, wtxt = tech.split("@")
            window = int(wtxt)
            t0 = time.time()
            lead = H.lead_of(gate)
            ev = H.evaluate(self.m, self.goal, lead, gate, window=window)
            if ev["pass"]:
                pooled = {c.get("fo_imm", c["fo"]): c for c in ev["cands"]}
                for organ in H.ORGANS_ORDER:
                    if organ == lead:
                        continue
                    e2 = H.evaluate(self.m, self.goal, organ, gate, window=window)
                    for c in e2["cands"]:
                        pooled.setdefault(c.get("fo_imm", c["fo"]), c)
                ev = dict(ev, cands=sorted(pooled.values(), key=lambda x: -x["_s"]))
            used = time.time() - t0

            fresh = [c for c in ev["cands"]
                     if ("0x%x" % c.get("fo_imm", c["fo"])) not in self.seen]
            for c in fresh:
                self.seen.add("0x%x" % c.get("fo_imm", c["fo"]))
            q = H._quality(ev, 3)
            reward = (4 if ev["cands"] else -5) + min(len(fresh), 6)
            if ev["cands"]:
                reward = reward - 2 + round(q * 2)
            reward = max(-5, min(10, reward))
            self.g.record(reward / 10.0,
                          gene=seg,
                          action={"gate": gate, "window": window, "tech": tech},
                          why=ev["why"])
            self.g.update_surface(tech, reward / 10.0, bool(ev["cands"]),
                                  sig=H.goal_sig(self.goal))
            self.iters += 1
            log.append({"pick": "%s@%d" % (gate, window), "n": len(ev["cands"]),
                        "fresh": len(fresh), "reward": reward,
                        "pass": ev["pass"], "why": ev["why"],
                        "used_s": round(used, 2)})
        self._save_state()
        return {"ok": True, "iter": self.iters, "steps": log,
                "pressure": round(self.g.pressure, 3),
                "strategy": self.g.strategy_mode, "seen": len(self.seen)}

    def op_techs(self, req):
        return {"ok": True, "techs": json.loads(json.dumps(self.g.tech_stats)),
                "weights": {t: self.g.tech_weight(t) for t in self.g.tech_stats},
                "report": self.g.surface_report()}

    def op_state(self, req):
        err = self._guard()
        return err or {"ok": True, "iters": self.iters,
                       "elapsed_s": round(time.time() - self.t0, 1),
                       "goal": self.goal, "seen": len(self.seen),
                       "gene": self.g.snapshot()}

    def op_land(self, req):
        err = self._guard()
        if err:
            return err
        site = _iv(req.get("site"))
        to = _iv(req.get("to"))
        if site is None or to is None:
            return {"ok": False, "err": "要 site 和 to"}
        width = int(req.get("width") or self.goal.get("width") or 1)
        off = site
        if off >= 0x1000000:
            off = off - self.m["base"]
        if not (0 <= off < os.path.getsize(self.path)):
            return {"ok": False, "err": "site 不在文件里"}

        try:
            raw = open(self.path, "rb").read()
        except PermissionError:
            return {"ok": False, "err": "exe 被占用（游戏开着），文件没动"}
        orig = raw[off:off + width]
        if len(orig) != width:
            return {"ok": False, "err": "site 越界"}
        try:
            newb = int(to).to_bytes(width, "little", signed=False)
        except OverflowError:
            return {"ok": False, "err": "%s 装不进 %d 字节" % (to, width)}
        if orig == newb:
            return {"ok": False, "err": "那里已经是 %s 了，没动" % to}

        if self.seen and ("0x%x" % off) not in self.seen:
            return {"ok": False,
                    "err": "site 0x%x 不是这次 ask/step 出来的站点，先问出来再落" % off}

        bakdir = os.path.join(ROOT, "var", "backups")
        archdir = os.path.join(ROOT, "var", "archives")
        os.makedirs(bakdir, exist_ok=True)
        os.makedirs(archdir, exist_ok=True)
        md5b = hashlib.md5(raw).hexdigest()
        bakf = os.path.join(bakdir, os.path.basename(self.path) + "." + md5b[:12] + ".bak")
        if not os.path.exists(bakf):
            shutil.copy2(self.path, bakf)

        buf = bytearray(raw)
        buf[off:off + width] = newb
        try:
            f = open(self.path, "r+b")
        except PermissionError:
            return {"ok": False, "err": "exe 被占用（游戏开着），文件没动"}
        with f:
            f.seek(0)
            f.write(buf)
            f.flush()
            os.fsync(f.fileno())

        back = open(self.path, "rb").read()
        got = back[off:off + width]
        ok = got == newb
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        aid = "%s_%s" % (ts, self.goal.get("name") or "serve_land")
        json.dump({"id": aid, "path": self.path, "backup": bakf,
                   "file_md5_before": md5b,
                   "file_md5_after": hashlib.md5(back).hexdigest(),
                   "ops": [{"where": "0x%x" % off, "width": width,
                            "orig": orig.hex(), "new": newb.hex(),
                            "orig_i": int.from_bytes(orig, "little"),
                            "new_i": int(to)}], "ok": ok},
                  open(os.path.join(archdir, aid + ".json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        if ok:
            try:
                AR.remember(self.md5, self.goal, ["0x%x" % off],
                            readback=int.from_bytes(got, "little"),
                            name=os.path.basename(self.path))
            except Exception as e:
                import sys as _s; print("archive 写入失败：%r" % (e,), file=_s.stderr)
        return {"ok": ok, "site": "0x%x" % off, "width": width,
                "from": int.from_bytes(orig, "little"), "to": int(to),
                "readback": int.from_bytes(got, "little"),
                "backup": bakf, "archive": aid,
                "rollback": 'copy "%s" "%s"' % (bakf, self.path)}

    def op_map(self, req):
        import mapbook
        q = req.get("q")
        if q:
            book = mapbook.search(mapbook.collect(), q)
            rows = [{"name": k, "kind": v["kind"], "sites": len(v["ops"]),
                     "ops": [{"site": hex(o["site"]), "w": o["width"],
                              "from": o.get("from"), "to": o.get("to")} for o in v["ops"][:20]]}
                    for k, v in sorted(book.items())]
            return {"ok": True, "op": "map", "q": q, "n": len(rows), "rows": rows}
        out = req.get("out") or os.path.join("地图", "全图")
        got = mapbook.export(out)
        got["op"] = "map"
        return got

    def op_near(self, req):
        import inspect_ops
        m = inspect_ops._m(self, req)
        if m is None:
            return {"ok": False, "err": "没有 map，先 start 或给 exe"}
        va = req.get("va")
        if va is None:
            return {"ok": False, "err": "没给 va"}
        rows = inspect_ops.near(m, int(str(va), 0), int(req.get("n") or 16))
        return {"ok": True, "op": "near", "va": str(va), "n": len(rows), "rows": rows}

    def op_refs(self, req):
        import inspect_ops
        m = inspect_ops._m(self, req)
        if m is None:
            return {"ok": False, "err": "没有 map，先 start 或给 exe"}
        va = req.get("va")
        if va is None:
            return {"ok": False, "err": "没给 va"}
        rows = inspect_ops.refs(m, int(str(va), 0))
        return {"ok": True, "op": "refs", "va": str(va), "n": len(rows), "rows": rows}

    def op_explain(self, req):
        import inspect_ops
        m = inspect_ops._m(self, req)
        if m is None:
            return {"ok": False, "err": "没有 map，先 start 或给 exe"}
        site = req.get("site")
        if site is None:
            return {"ok": False, "err": "没给 site"}
        return inspect_ops.explain(m, int(str(site), 0))

    def op_stop(self, req):
        return {"ok": True, "bye": True, "iters": self.iters}

    def _save_state(self):
        try:
            os.makedirs(os.path.join(ROOT, "var"), exist_ok=True)
            self.g.save(os.path.join(ROOT, "var", "var/geda_state.json"))
        except Exception:
            pass


if _LIVE:
    _LIVE.attach_live(Engine)


def serve():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    eng = Engine()
    _out({"ok": True, "hello": "新逆流常驻进程", "ops": list(OPS),
          "gates": list(H.GATES_ORDER),
          "hint": "先 start{exe,from,to}，再 ask{kind:'auto'} 或 step{n}；每行一个 JSON"})
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            _out({"ok": False, "err": "JSON 解不动：%s" % e})
            continue
        op = req.get("op")
        fn = getattr(eng, "op_" + str(op), None)
        if fn is None:
            _out({"ok": False, "err": "不认识的 op：%s" % op})
            continue
        try:
            _out(fn(req))
        except Exception as e:
            _out({"ok": False, "err": "%s: %s" % (type(e).__name__, e)})
        if op == "stop":
            break


def _ev_brief(ev, limit=6):
    if not isinstance(ev, dict):
        return ""
    keys = ("gate", "stride", "delta", "votes", "gcd", "lift", "table",
            "table_names", "f64", "f32", "byte", "ratio", "arm", "cmp_imm",
            "base", "disp", "refs", "consumer", "sign")
    parts = []
    for k in keys:
        v = ev.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, list):
            v = ",".join(str(x) for x in v[:4])
        parts.append("%s=%s" % (k, v))
    return " ".join(parts[:limit])


def change(argv):
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        prog="python niliu.py change",
        description="给 exe + 原值 + 新值，一条命令找站点（默认只看不写）")
    ap.add_argument("exe")
    ap.add_argument("from_", metavar="from", type=lambda s: int(s, 0))
    ap.add_argument("to", type=lambda s: int(s, 0))
    ap.add_argument("--width", type=lambda s: int(s, 0), default=None,
                    help="要改几字节；默认听引擎回执里的 site_width")
    ap.add_argument("--kind", default="auto",
                    help="auto/record/imm/arm/typed/f32/addimm/idtable/typedref/incdec/dataval")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--name", default="change")
    ap.add_argument("--write", action="store_true", help="落第 1 条（备份+回读+档案）")
    ap.add_argument("--json", action="store_true", help="只输出一行原始 JSON")
    a = ap.parse_args(argv)

    eng = Engine()
    req = {"exe": a.exe, "from": a.from_, "to": a.to, "name": a.name}
    if a.width:
        req["width"] = a.width
    st = eng.op_start(req)

    if a.json:
        out = {"start": st}
        if not st.get("ok"):
            _out(out)
            return 2
        ask = eng.op_ask({"kind": a.kind, "top": a.top})
        out["ask"] = ask
        if a.write and ask.get("ok") and ask.get("rows"):
            row = ask["rows"][0]
            w = int(ask.get("site_width") or a.width or st["goal"]["width"])
            out["land"] = eng.op_land({"site": row["site"], "to": a.to, "width": w})
        _out(out)
        return 0 if ask.get("ok") else 1

    if not st.get("ok"):
        print("× %s" % st.get("err"))
        return 2

    prof = st.get("profile") or {}
    print("逆流 change   %s → %s%s" % (a.from_, a.to,
          "   (width=%d)" % a.width if a.width else ""))
    print("  exe     %s" % st.get("exe"))
    print("  摸底    %s / %s / cmp链 %s / 跳表 %s / 名字表 %s / 浮点 %s"
          % (prof.get("arch", "?"), prof.get("toolchain", "?"),
             prof.get("cmp_imm", "?"), prof.get("jt", "?"),
             prof.get("tables", "?"), prof.get("float_ops", "?")))
    ready = (st.get("presets") or {}).get("ready") or []
    gaps = (st.get("presets") or {}).get("gaps") or []
    if ready:
        print("  能打    %s" % "、".join(ready))
    for g in gaps:
        print("  缺口    %s（%s）" % (g.get("名字"), g.get("缺口")))
    if (st.get("archive") or {}).get("recall"):
        print("  档案    这个目标以前落过盘，ask 回执里会带 recall")

    ask = eng.op_ask({"kind": a.kind, "top": a.top})
    if not ask.get("ok"):
        print("\n× %s" % ask.get("err"))
        if ask.get("reasons"):
            for r in ask["reasons"][:5]:
                print("  %s" % r)
        print("\n换个判据再试：--kind imm / addimm / idtable / typedref / incdec / dataval")
        return 1

    rows = ask.get("rows") or []
    w = ask.get("site_width") or a.width or st["goal"]["width"]
    print("\n判据 %s   候选 %d 条   %.2f s"
          % (ask.get("gate"), ask.get("n", len(rows)), ask.get("used_s") or 0))
    if ask.get("recall"):
        rc = ask["recall"]
        print("  历史：%s -> %s 改过 %s" % (rc.get("goal"), rc.get("readback"),
                                          ",".join(rc.get("sites") or [])))
    print("  %-3s %-12s %-4s %-6s %s" % ("#", "站点", "宽", "分", "说明"))
    for i, row in enumerate(rows, 1):
        print("  %-3d %-12s %-4s %-6s %s"
              % (i, row.get("site"), w, row.get("score"), row.get("text")))
        ev = _ev_brief(row.get("evidence"))
        if ev:
            print("      证据 %s" % ev)

    if ask.get("n", len(rows)) > len(rows):
        print("\n共 %d 条，这里只显示 %d 条；同一张表/同一列往往要逐格改，一次只落一处。"
              % (ask["n"], len(rows)))
    if not a.write:
        print("\n未改文件。确认后加 --write 落第 1 条。")
        return 0

    row = rows[0]
    print("\n落盘 %s  width=%s  to=%s" % (row.get("site"), w, a.to))
    lr = eng.op_land({"site": row.get("site"), "to": a.to, "width": w})
    if not lr.get("ok"):
        print("× %s" % lr.get("err"))
        if "装不进" in str(lr.get("err")):
            print("  这个站点只有 %s 字节。确认目标宽度后：--width N" % w)
        return 1
    print("  原值 %s → 新值 %s   回读 %s"
          % (lr.get("from"), lr.get("to"), lr.get("readback")))
    print("  备份 %s" % lr.get("backup"))
    print("  档案 %s" % lr.get("archive"))
    print("  回滚 cp -f \"%s\" \"%s\"" % (lr.get("backup"), st.get("exe")))
    print("\n重启游戏再看效果。没变就换判据，不要在原地连按 --write。")
    return 0


def task(path):
    job = json.load(open(path, encoding="utf-8"))
    ops = job.get("ops") if isinstance(job, dict) else job
    eng = Engine()
    for req in ops:
        op = req.get("op")
        fn = getattr(eng, "op_" + str(op), None)
        if fn is None:
            _out({"ok": False, "err": "不认识的 op：%s" % op, "op": op})
            continue
        try:
            out = fn(req)
        except Exception as e:
            out = {"ok": False, "err": "%s: %s" % (type(e).__name__, e)}
        out["op"] = op
        _out(out)
        if op == "stop":
            break


if __name__ == "__main__":
    act = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if act == "serve":
        serve()
    elif act == "change":
        raise SystemExit(change(sys.argv[2:]))
    elif act == "task":
        if len(sys.argv) < 3:
            raise SystemExit("用法：python niliu.py task jobs/xxx.json")
        task(sys.argv[2])
    else:
        raise SystemExit("用法：python niliu.py change <exe> <from> <to> [--write]\n"
                         "      python niliu.py serve\n"
                         "      python niliu.py task <job.json>")
