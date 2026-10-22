# -*- coding: utf-8 -*-
"""Decides whether a goal is best answered by a table class or a code class."""
from __future__ import annotations

import rules
import tree as TR

CODE_MIN_SITES = rules.get("class.code_min_sites", 3)


def _class_state(cls, a, goal):
    rows = (a or {}).get("cands") or []
    evs = [r.get("evidence") or {} for r in rows]
    st = {"arm_n": 0, "rec_n": 0, "rec_names": False, "rec_gcd": 0,
          "arm_arms": 0, "from_pct25": 0, "is_half": False}
    a0, b0 = goal.get("from"), goal.get("to")
    st["from_pct25"] = 1 if a0 and a0 % 25 == 0 else 0
    st["is_half"] = bool(b0 and b0 * 2 in (a0, (a0 or 0) - 1))
    if cls == "record":
        st["rec_n"] = len(rows)
        st["rec_names"] = any(e.get("table_names") for e in evs)
        st["rec_gcd"] = max([e.get("gcd") or 0 for e in evs] or [0])
    else:
        st["arm_n"] = len(rows)
        st["arm_arms"] = max([e.get("arms") or 0 for e in evs] or [0])
    return st


def _selfcheck(cls, a):
    rows = (a or {}).get("cands") or []
    evs = [r.get("evidence") or {} for r in rows]
    if cls == "record":
        return bool(rows) and len(rows) >= 3 and any(e.get("table_names") for e in evs)
    pure = sum(1 for e in evs if e.get("acc") == "pure")
    return len(rows) >= 2 and pure * 2 >= len(evs)


def pick_class(answers, code_min=CODE_MIN_SITES, tree_=None, goal=None):
    arm = answers.get("arm")
    rec = answers.get("record")
    tab = answers.get("table")

    s_rec = 4.0
    s_arm = 3.0 + (1.2 if (arm and len(arm["cands"]) >= code_min) else 0.0)

    boost = TR.boost_of()
    if tree_ is not None and boost > 0 and arm and goal is not None:
        p_arm = tree_.predict(_class_state("arm", arm, goal))
        p_rec = tree_.predict(_class_state("record", rec, goal)) if rec else None
        s_arm += boost * (p_arm if p_arm is not None else 0.0)
        s_rec += boost * (p_rec if p_rec is not None else 0.0)

    if arm and s_arm > s_rec:
        return arm
    if rec:
        return rec
    if arm:
        return arm
    typed = answers.get("typed")
    if typed:
        return typed
    return tab


class_state = _class_state
selfcheck = _selfcheck
