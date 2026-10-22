# -*- coding: utf-8 -*-
"""Optional decision tree (boost=0 by default: observes only)."""
from __future__ import annotations

import rules


class SimpleTree(object):

    class Node(object):
        __slots__ = ("feature", "left", "right", "pos", "neg")

        def __init__(self, feature=None):
            self.feature = feature
            self.left = None
            self.right = None
            self.pos = 0
            self.neg = 0

    def __init__(self, features, max_depth=3, min_samples=8):
        self.features = list(features)
        self.max_depth = max_depth
        self.min_samples = min_samples
        self.root = self.Node()
        self.samples = 0

    def _grow(self, node, samples, depth):
        pos = sum(1 for s in samples if s[1])
        node.pos, node.neg = pos, len(samples) - pos
        if depth >= self.max_depth or len(samples) < self.min_samples:
            return
        best, best_gain = None, 0.0
        base = abs(pos / float(len(samples)) - 0.5) * 2.0
        for name, fn in self.features:
            try:
                left = [s for s in samples if not fn(s[0])]
                right = [s for s in samples if fn(s[0])]
            except Exception:
                continue
            if not left or not right:
                continue
            pl = sum(1 for s in left if s[1]) / float(len(left))
            pr = sum(1 for s in right if s[1]) / float(len(right))
            gain = (abs(pl - 0.5) + abs(pr - 0.5)) - base
            gain *= min(len(left), len(right)) / float(len(samples))
            if gain > best_gain:
                best, best_gain = (name, fn, left, right), gain
        if best is None:
            return
        name, fn, left, right = best
        node.feature = name
        node.left, node.right = self.Node(), self.Node()
        self._grow(node.left, left, depth + 1)
        self._grow(node.right, right, depth + 1)

    def fit(self, samples):
        """samples: [(state, label)]，label True/False"""
        if not samples:
            return self
        self.samples = len(samples)
        self.root = self.Node()
        self._grow(self.root, list(samples), 0)
        return self

    def _leaf(self, node, state):
        while node.feature is not None:
            fn = dict(self.features).get(node.feature)
            go_right = bool(fn and fn(state))
            node = node.right if go_right else node.left
            if node is None:
                return None
        return node

    def predict(self, state):
        if self.samples < self.min_samples:
            return None
        leaf = self._leaf(self.root, state)
        if leaf is None or (leaf.pos + leaf.neg) == 0:
            return None
        return leaf.pos / float(leaf.pos + leaf.neg)

    def describe(self, depth=0, node=None, prefix=""):
        node = node if node is not None else self.root
        rows = []
        if node.feature is None:
            n = node.pos + node.neg
            rows.append("%s└─ 叶 %d/%d（正/总）" % (prefix, node.pos, n))
            return "\n".join(rows)
        rows.append("%s├─ 若 %s" % (prefix, node.feature))
        rows.append(self.describe(depth + 1, node.right, prefix + "│  "))
        rows.append("%s└─ 否则" % prefix)
        rows.append(self.describe(depth + 1, node.left, prefix + "   "))
        return "\n".join(rows)


def class_features(goal=None):
    goal = goal or {}

    def _n(x):
        return float(x or 0)

    return [
        ("代码答案≥3处", lambda s: _n(s.get("arm_n")) >= 3),
        ("代码答案≥5处", lambda s: _n(s.get("arm_n")) >= 5),
        ("表答案≥5处", lambda s: _n(s.get("rec_n")) >= 5),
        ("表答案≥10处", lambda s: _n(s.get("rec_n")) >= 10),
        ("表答案有名字锚", lambda s: bool(s.get("rec_names"))),
        ("表答案公因数≥5", lambda s: _n(s.get("rec_gcd")) >= 5),
        ("分档≥4档", lambda s: _n(s.get("arm_arms")) >= 4),
        ("原值是25的倍数", lambda s: _n(s.get("from_pct25")) >= 1),
        ("目标值是原值一半", lambda s: bool(s.get("is_half"))),
        ("代码答案比表少", lambda s: _n(s.get("arm_n")) < _n(s.get("rec_n"))),
    ]


def boost_of():
    return float(rules.get("tree.boost", 0.0) or 0.0)
