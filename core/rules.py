# -*- coding: utf-8 -*-
"""Loads rules/rules.json -- the single source of truth for every threshold."""
from __future__ import annotations

import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules", "rules.json")
_DEFAULT = {
    "record": {"min_gcd": 2, "min_ratio": 0.9, "min_lift": 5.0, "strong_votes": 3,
               "max_sites": 64, "table_min_len": 4, "filler_run": 3,
               "table_strides": list(range(8, 65, 4))},
    "arm": {"gate_min": 10.0, "acc_pure_bonus": 1.5, "acc_derived_penalty": 3.0,
            "acc_ahead": 20, "acc_back": 60},
    "class": {"code_min_sites": 3},
    "geda": {"prior": 4, "reward_gain": 10, "dyn_min": -50, "dyn_max": 1000,
             "boost_hit": 5, "boost_miss": 2, "boost_max": 100, "step_max": 8,
             "stall_threshold": 40, "doubt_threshold": 200, "hot_reward": 1.5,
             "exp_reward": 0.8, "hot_cap": 8, "exp_cap": 60, "hot_pick_p": 0.5,
             "reward_hit_new": 1.0, "reward_hit": 0.3, "reward_miss": -0.5,
             "reward_top_k": 3},
    "windows": [24, 32, 48, 64, 96], "rounds": 6, "seed": 20261017, "exam_top": 30,
    "guards": {"big_file_lines": 700, "min_organs": 5,
               "forbidden_dirs": ["cygwin64"]},
}

_R = {}


def load(override=None, path=None):
    global _R
    base = json.loads(json.dumps(_DEFAULT))
    p = path or PATH
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                user = json.load(f)
            _merge(base, user)
        except Exception as e:
            print("规则文件读不动（用默认值）：%s" % e)
    if override:
        _merge(base, override)
    _R = base
    return _R


def _merge(dst, src):
    for k, v in (src or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def get(path, default=None):
    if not _R:
        load()
    cur = _R
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def all():
    if not _R:
        load()
    return _R


load()
