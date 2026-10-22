# -*- coding: utf-8 -*-
"""Tick / deterministic RNG / agent scaffolding."""
from __future__ import annotations

import time
import zlib


class Rng(object):

    def __init__(self, seed=20261017):
        self.seed = int(seed) & 0xFFFFFFFF
        self.reset()

    def reset(self):
        self.state = self.seed or 0x9E3779B9
        self.calls = 0
        return self

    def next(self):
        """[0,1)"""
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        self.calls += 1
        return self.state / 0x80000000

    def int(self, n):
        return int(self.next() * max(1, n)) % max(1, n)

    def range(self, a, b):
        return a + self.next() * (b - a)

    def pick(self, arr):
        return arr[self.int(len(arr))] if arr else None

    def chance(self, p):
        return self.next() < p

    def uniform(self, a=0.0, b=1.0):
        return a + self.next() * (b - a)

    def random(self):
        return self.next()

    def choice(self, seq):
        return seq[self.int(len(seq))] if seq else None


class Agent(object):

    def __init__(self, aid="agent-0", fn=None, max_iters=1, history_cap=200):
        self.id = aid
        self.fn = fn
        self.max_iters = max_iters
        self.history_cap = history_cap
        self.state = "idle"
        self.iters = 0
        self.rewards = []
        self.history = []
        self.started_at = None
        self.halted_at = None
        self.last_error = None

    def boot(self):
        self.state = "running"
        self.started_at = time.time()
        return self

    def step(self, *a, **kw):
        if self.state != "running":
            self.boot()
        try:
            rec = self.fn(self, *a, **kw) if self.fn else {}
            self.iters += 1
            self.rewards.append(float(rec.get("reward", 0.0)))
            self.history.append(rec)
            self.history = self.history[-self.history_cap:]
            return rec
        except Exception as e:
            self.crash(e)
            return {"error": str(e)}

    def halt(self):
        self.state = "halted"
        self.halted_at = time.time()
        return self

    def crash(self, err):
        self.state = "crashed"
        self.last_error = str(err)
        self.halted_at = time.time()
        return self

    def avg_reward(self, n=None):
        xs = self.rewards[-n:] if n else self.rewards
        return sum(xs) / len(xs) if xs else 0.0

    def describe(self):
        return {"id": self.id, "state": self.state, "iters": self.iters,
                "avg_reward": round(self.avg_reward(), 3),
                "error": self.last_error}


class Tick(object):

    def __init__(self, seed=20261017, on_phase=None):
        self.id = "tick-%08x" % (zlib.crc32(str(seed).encode()) & 0xFFFFFFFF)
        self.seed = seed
        self.rng = Rng(seed)
        self.phases = []
        self.data = {}
        self.errors = []
        self.log = []
        self.on_phase = on_phase
        self.state = "idle"
        self.started_at = None

    def boot(self):
        self.state = "running"
        self.started_at = time.time()
        self.rng.reset()
        return self

    def phase(self, name, fn, **opts):
        self.phases.append({"name": name, "fn": fn, "opts": opts})
        return self

    def run(self, **ctx):
        if self.state != "running":
            self.boot()
        for i, ph in enumerate(self.phases):
            t0 = time.time()
            try:
                out = ph["fn"](self, **ctx) or {}
                if isinstance(out, dict):
                    self.data.update(out)
                rec = {"phase": ph["name"], "idx": i, "ok": True,
                       "used_s": round(time.time() - t0, 3)}
            except Exception as e:
                import traceback
                self.errors.append({"phase": ph["name"], "error": str(e),
                                    "where": traceback.format_exc().splitlines()[-3:]})
                rec = {"phase": ph["name"], "idx": i, "ok": False,
                       "used_s": round(time.time() - t0, 3), "error": str(e)}
            self.log.append(rec)
            if self.on_phase:
                self.on_phase(rec)
        self.state = "done"
        return self.data

    def serialize(self):
        return {"kind": "niliu.tick", "id": self.id, "seed": self.seed,
                "state": self.state, "phases": [p["name"] for p in self.phases],
                "log": self.log, "errors": self.errors,
                "data_keys": list(self.data)}
