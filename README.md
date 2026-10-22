# niliu

**Give it a vague goal (`from` → `to`), get back a few evidence-backed sites; land one and it backs up, verifies and hands you a rollback command.**

`niliu` (逆流, "counter-current") is a binary-patching engine for single-player games. You do not read
assembly. You do not guess addresses. You state the value you see on disk and the value you want, and the
engine returns a short list of candidate sites, each with the evidence that let it through a gate.

```
python niliu.py change "E:/games/PlantsVsZombies.exe" 25 50
```

```
niliu change   25 -> 50
  exe     E:\games\PlantsVsZombies.exe
  probe   32-bit x86 / native Win32 / cmp-chain 20423 / jump-table 0 / name-table 23 / f64 17412
  ready   switch-case constants, name-anchored tables, pointer-walk loops, f64 constants
  gaps    virtual calls (prov), object-init runs, f32, i32/i16/i8 widths, string-hash dispatch

gate arm   4 candidates   3.49 s
  #   site          width  score  what
  1   0x309f0       4      14.0   mov ecx, 0x19
      evidence gate=arm
  2   0x1b9b8       4      13.5   mov eax, 0x19
      evidence gate=arm
  3   0x5855d       4      13.0   mov dword ptr [esi + 0x20], 0x19
      evidence gate=arm
  4   0x329a9       4      12.0   mov eax, 0x19
      evidence gate=arm

No bytes written. Add --write to land candidate #1.
```

> Real output from a PvZ 1.0.0.1051 binary on 2026-10-23 (paths shortened, labels translated).

---

> **Recommended:** drive it with an LLM agent using the bundled [skill](skill/). You state goals;
> the engine finds, ranks and verifies the sites, then hands back a rollback command.

## 30 seconds

```bash
# 1. dependency (only one)
pip install -r requirements.txt

# 2. dry run: find candidates, touch nothing
python niliu.py change "D:/games/x.exe" 150 75

# 3. land candidate #1: backup -> write -> independent read-back -> archive -> rollback cmd
python niliu.py change "D:/games/x.exe" 150 75 --write

# 4. restart the game and look at that one thing
```

| flag | meaning |
|---|---|
| `--write` | actually patch the file (default is dry run) |
| `--width N` | force the byte width; defaults to the width reported by the engine |
| `--kind K` | `auto` (default), `record`, `imm`, `arm`, `typed`, `f32`, `addimm`, `idtable`, `typedref`, `incdec`, `dataval` |
| `--top N` | how many candidates to show (default 8) |
| `--json` | one-line raw JSON for other programs |

Every guard still applies: dry run by default, only the first candidate is landed, and success means
`read-back == to`. Nothing is written twice.

---

## What it can find today

| Target | Gate | Example |
|---|---|---|
| price / HP in a named struct table | `record` | cost 150 -> 75 |
| typed initial values / switch-case constants | `arm` | sun 25 -> 50 |
| a single `mov [obj+disp], imm` constant | `imm` | chew 4000, fire rate 200 |
| a constant subtracted per event | `addimm` | 4 damage per bite |
| a counter that goes -1 per frame | `incdec` | cooldown ticks |
| anonymous type tables (value column + incrementing id) | `idtable` | `damage[type]` / `hp[type]` |
| an f64 constant (patch one byte) | `typed` | 400.0 -> 100.0 |
| a referenced f64 multiplier | `typedref` | 0.4 -> 0.1 |
| an f32 constant | `f32` | 0.23 -> 0.46 |
| a plain C global | `dataval` | `int g_hp = 100;` |

Ranking is GEDA's job (weighted roulette over techniques, fed by measured outcomes). Organs only supply
evidence. `probe` tells you which shapes this binary has, and `presets.gaps` lists what is still out of
reach — do not fight the engine on those.

---

## How it works

```
goal {from, to, width}
   |
   v
organs  ...  find candidate sites, each with evidence           (13 organs)
   |
   v
gates   ...  accept or reject a candidate                       (10 gates)
   |
   v
GEDA    ...  rank accepted sites, learn which technique pays    (weighted roulette + reward)
   |
   v
land    ...  backup -> write -> independent read-back -> archive -> rollback command
```

- **Organs** are registered, not hard-coded: `registry.py` + `@R.organ`.
- **Gates** are contracts with a documented record format; a gate that cannot answer says so.
- **Every landed byte** is archived with the pre-patch md5, so `--restore` and a manual `cp -f` both work.

---

## Layout

```
niliu.py            the only entry point: change / serve / task
core/               engine (25 modules)
  hunt.py           pipeline: recon -> enum -> rank -> refine
  geda.py           weighted roulette, technique weights, reward pool
  map.py            PE parser + disassembler + indexes
  registry.py       self-registration for organs / gates / policies
  typed.py ...      organ modules (13 organs total)
  inspect_ops.py    near / refs / explain (read-only)
  live_ops.py       live-process read-only ops
  archive.py        per-exe archive: structures + target history
  profile.py        probe -> preset selection -> ready / gaps
  exam.py           18-paper exam against PvZ ground truth
  replay.py         replay a known byte list
rules/              rules.json (every threshold), presets.json (13 shapes)
skill/              installable Agent Skill: SKILL.md (EN) + SKILL.zh-CN.md (ZH)
docs/               usage, design, skill card, changelog
examples/           three job files, edit the path and run
tools/              guard.py (12 structural guards), survey.py (probe one exe)
tests/              generality.py + synthetic C target and prebuilt binaries
facts/              PvZ ground truth used by the exam
var/                runtime output (backups, archives, maps); git-ignored
```

Runtime paths are `var/` (backups, archives, caches) and `rules/`; nothing writes outside the project.

---

## Docs

| File | Audience |
|---|---|
| [docs/USAGE.md](docs/USAGE.md) | full workflow, 22 ops, 10 gates, failure diagnosis |
| [docs/USAGE.zh-CN.md](docs/USAGE.zh-CN.md) | 中文完整用法（与英文版同源） |
| [docs/DESIGN.md](docs/DESIGN.md) | why the engine is built this way |
| [docs/SKILL.md](docs/SKILL.md) | compact execution card for an LLM agent |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | measured capability changes |
| [skill/](skill/) | installable Agent Skill (EN/ZH): prerequisites, 22 ops, 10 gates |

---

## Verification

```bash
python tools/guard.py        # 12 structural guards
python core/exam.py <pvz.exe> 30   # 18 papers (needs a PvZ 1.0.0.1051 binary)
python tests/generality.py   # synthetic C target, needs gcc + x86_64-w64-mingw32-gcc
```

Measured on 2026-10-23:

```
guards      12 / 12 green
exam        14 / 18 full marks, mean F1 0.778
generality   4 / 6  (tables OK, floats OK, switch-case constants not found)
```

These are floors, not a graduation. The graduation line is exam 18/18 **and** generality 6/6.

---

## Limits

- **Jump-table switches** (gcc / clang / MSVC 2015+): `gate_jt` not implemented; `arm` only walks `cmp` chains.
- **Virtual calls / object identity**: `prov` missing — the engine cannot tell the same `disp` on two objects apart.
- **i16 / i8 constants**: only f64 / f32 byte patching exists.
- **Unity IL2CPP / Mono / ARM64 / ELF**: PE + x86/x64 only.
- **Live memory writes**: `live_*` is read-only; patching still goes through disk.
- **No restart-free patching**, and no guarantee the field is read by the game.
- **`from = 0`** is rejected (treated as "not given").

---

## License

MIT — see [LICENSE](LICENSE). Free to use, modify, redistribute and sell, with attribution.

> **One line:** state `from -> to`, get evidence-backed sites, land one, get a verified patch and a rollback.
