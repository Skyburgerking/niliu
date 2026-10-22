# -*- coding: utf-8 -*-
"""GEDA core: weighted roulette over techniques, reward bookkeeping, hot genes."""
from __future__ import annotations

import json
import os
import random

import rules

BASES = ["A", "G", "C", "T", "X"]
COMPLEMENT = {"A": "T", "T": "A", "G": "C", "C": "G", "X": "X"}


class GedaCore(object):

    def __init__(self, gene_len=60, memory_capacity=40, seed=None):
        if seed is not None:
            random.seed(seed)
        self.gene_len = gene_len
        self.gene_primary = "".join(random.choice(BASES) for _ in range(gene_len))
        self.gene_complementary = "".join(COMPLEMENT[b] for b in self.gene_primary)
        self.doubt_chain = "".join(random.choice(BASES) for _ in range(gene_len // 3))
        self.memory_pool = []          # [(segment, utility)]
        self.memory_capacity = memory_capacity
        self.pressure = 0.5
        self.strategy_mode = "balanced"
        self.streak = 0
        self.history = []              # [{gene, action, fitness, why}]
        self.clue_weights = {}
        self.dyn_weight = {}
        self.boost = {}
        self.tech_stats = {}
        self.step_size = {}
        self.experiences = []
        self.hot_genes = []
        self.stall = 0
        self.stall_threshold = rules.get("geda.stall_threshold", 40)
        self.doubt = 0
        self.doubt_threshold = rules.get("geda.doubt_threshold", 200)
        self.force_explore = False
        self.best_reward = 0.0

    def _get_active_strand(self):
        if self.strategy_mode == "exploitative" and self.memory_pool:
            return self.memory_pool[0][0].ljust(self.gene_len, "G")
        if self.pressure < 0.3:
            return self.gene_complementary
        if self.pressure > 0.7:
            return self.gene_primary
        return self.gene_primary if random.random() < 0.5 else self.gene_complementary

    def get_gene_segment(self, n=6):
        active = self._get_active_strand()
        start = random.randrange(max(1, len(active) - n))
        seg = active[start:start + n]
        if random.random() < 0.1 + self.pressure * 0.1:
            i = random.randrange(n)
            seg = seg[:i] + random.choice(BASES) + seg[i + 1:]
        return seg

    def record(self, fitness, gene=None, action=None, why=""):
        self.pressure = max(0.05, min(1.0, self.pressure * 0.9 + (1 - fitness) * 0.3))
        self.streak = self.streak + 1 if fitness > 0.6 else 0
        if self.streak > 5:
            self.strategy_mode = "exploitative"
        elif self.pressure > 0.6:
            self.strategy_mode = "exploratory"
        else:
            self.strategy_mode = "balanced"
        if gene:
            self.reward_segment(gene, fitness)
        self.history.append({"gene": gene, "action": action,
                             "fitness": round(fitness, 3), "why": why})
        self.history = self.history[-200:]

    def reward_segment(self, segment, utility):
        segment = segment[:8]
        for i, (seg, u) in enumerate(self.memory_pool):
            if seg == segment:
                self.memory_pool[i] = (seg, min(1.0, u + 0.1))
                break
        else:
            self.memory_pool.append((segment, min(1.0, utility)))
        self.memory_pool.sort(key=lambda x: -x[1])
        self.memory_pool = self.memory_pool[:self.memory_capacity]

    def snapshot(self):
        return {"gene_primary": self.gene_primary, "pressure": self.pressure,
                "strategy_mode": self.strategy_mode, "streak": self.streak,
                "memory_pool": self.memory_pool,
                "clue_weights": self.clue_weights, "dyn_weight": self.dyn_weight,
                "boost": self.boost, "tech_stats": self.tech_stats}

    def save(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=1)

    def load(self, path):
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.gene_primary = d.get("gene_primary", self.gene_primary)
        self.gene_complementary = "".join(COMPLEMENT[b] for b in self.gene_primary)
        self.pressure = d.get("pressure", self.pressure)
        self.strategy_mode = d.get("strategy_mode", self.strategy_mode)
        self.streak = d.get("streak", self.streak)
        self.memory_pool = [tuple(x) for x in d.get("memory_pool", [])]
        self.clue_weights.update(d.get("clue_weights") or {})
        self.dyn_weight.update(d.get("dyn_weight") or {})
        self.boost.update(d.get("boost") or {})
        self.tech_stats.update(d.get("tech_stats") or {})
        return True

    def register_tech(self, tech, prior=None):
        if prior is None:
            prior = rules.get("geda.prior", 4)
        if tech not in self.clue_weights:
            self.clue_weights[tech] = prior
            self.dyn_weight[tech] = prior
            self.boost[tech] = 0
            self.tech_stats[tech] = {"n": 0, "hit": 0, "reward": 0.0}
        return tech

    def tech_weight(self, tech):
        return max(1, self.clue_weights.get(tech, 4)
                   + self.dyn_weight.get(tech, 4) + self.boost.get(tech, 0))

    def pick_tech(self, techs, rng=None):
        techs = [t for t in techs if t]
        if not techs:
            return None
        if len(techs) == 1:
            return techs[0]
        total = sum(self.tech_weight(t) for t in techs)
        u = (rng or random).uniform(0, total)
        acc = 0.0
        for t in techs:
            acc += self.tech_weight(t)
            if u <= acc:
                return t
        return techs[-1]

    def update_tech(self, tech, reward, hit):
        self.register_tech(tech)
        st = self.tech_stats[tech]
        st["n"] += 1
        st["hit"] += 1 if hit else 0
        st["reward"] += reward
        self.dyn_weight[tech] = max(rules.get("geda.dyn_min", -50),
                                    min(rules.get("geda.dyn_max", 1000),
                                        self.dyn_weight[tech]
                                        + int(round(reward * rules.get("geda.reward_gain", 10)))))
        if hit:
            self.boost[tech] = min(rules.get("geda.boost_max", 100),
                                   self.boost[tech] + rules.get("geda.boost_hit", 5))
        else:
            self.boost[tech] = max(0, self.boost[tech] - rules.get("geda.boost_miss", 2))
        return self.dyn_weight[tech]

    def tech_report(self):
        rows = []
        for t, st in sorted(self.tech_stats.items(),
                            key=lambda kv: -kv[1]["reward"]):
            rows.append("%-28s w=%4d n=%-3d hit=%-3d reward=%7.1f"
                        % (t, self.tech_weight(t), st["n"], st["hit"], st["reward"]))
        return "\n".join(rows)

    def update_surface(self, tech, reward, hit, sig=None):
        self.register_tech(tech)
        self.step_size.setdefault(tech, 1)
        self.update_tech(tech, reward, hit)
        if hit:
            self.step_size[tech] = min(rules.get("geda.step_max", 8),
                                       self.step_size[tech] + 1)
            self.stall = 0
            self.doubt = 0
        else:
            self.step_size[tech] = max(1, self.step_size[tech] - 1)
            self.stall += 1
            self.doubt += 1
        if reward >= self.best_reward:
            self.best_reward = reward
            self.stall = 0
        if self.stall >= self.stall_threshold:
            self.force_explore = True
            self.stall = 0
        if self.doubt >= self.doubt_threshold:
            for t in self.dyn_weight:
                self.dyn_weight[t] = self.clue_weights.get(t, 4)
                self.boost[t] = 0
            self.doubt = 0
            self.force_explore = True
        if hit and reward >= rules.get("geda.exp_reward", 0.8):
            rec = (sig or "", tech, round(reward, 2))
            if rec not in self.experiences:
                self.experiences.append(rec)
                self.experiences = self.experiences[-rules.get("geda.exp_cap", 60):]
            if reward >= rules.get("geda.hot_reward", 1.5):
                self.hot_genes.append(rec)
                self.hot_genes = sorted(self.hot_genes, key=lambda x: -x[2])[:rules.get("geda.hot_cap", 8)]
        return self.dyn_weight[tech]

    def pick_surface(self, techs, rng=None):
        techs = [t for t in techs if t]
        if not techs:
            return None
        if self.force_explore:
            self.force_explore = False
            return (rng or random).choice(techs)
        hot = [h for h in self.hot_genes if h[1] in techs]
        if hot and (rng or random).random() < rules.get("geda.hot_pick_p", 0.5):
            return hot[0][1]
        return self.pick_tech(techs, rng)

    def surface_report(self):
        rows = []
        for t, st in sorted(self.tech_stats.items(),
                            key=lambda kv: -kv[1]["reward"]):
            rows.append("%-14s w=%4d step=%d n=%-3d hit=%-3d reward=%6.1f"
                        % (t, self.tech_weight(t), self.step_size.get(t, 1),
                           st["n"], st["hit"], st["reward"]))
        if self.hot_genes:
            rows.append("热点基因：" + "、".join("%s(%s)" % (h[1], h[2])
                                              for h in self.hot_genes[:5]))
        return "\n".join(rows)
