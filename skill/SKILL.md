---
name: niliu-injection-engine
description: Drive the niliu engine to change values in single-player game binaries without reading assembly. You emit JSON (start/ask/step/land), the engine finds evidence-backed sites and patches with backup + read-back + rollback. Use for HP, cost, cooldown, damage, speed, counts; when a value's origin is unknown; when a patch had no effect; to roll back a broken patch; or to judge whether a game is tractable. Requires the niliu engine (github.com/Skyburgerking/niliu) and an LLM agent with tool use. Keywords: niliu, game patching, binary patch, PE x86/x64, from-to, start, ask, step, land, gate, organ, record, imm, arm, typed, f32, addimm, idtable, typedref, incdec, dataval, GEDA, weighted roulette, evidence, read-back, rollback, archive, jump table, virtual call, PvZ.
---

# niliu v3 — execution card

> Engine: **github.com/Skyburgerking/niliu** (there is only one version).
> This page is the card for an **LLM agent**, not a hand-patching manual.
> When this card and the engine disagree, the engine's `{"op":"help"}` response wins.

---

## Before you start (prerequisites)

1. **Use an LLM agent for the work.** This card assumes a model with tool use that can call the
   engine and read JSON receipts. Manual assembly reading is explicitly out of scope.
2. **Install the engine** (see its README): Python 3.10+, `capstone>=5.0`, Windows, PE x86/x64 target.
3. **Own the game.** Single-player titles only, for personal use and study. No online, competitive or
   commercial cheating. You are responsible for what you patch.
4. **Back up the exe.** The engine backs up automatically on `land`, but keep your own copy too.
5. **Close the game** before patching: a running process locks the file.

---

## Three iron rules

1. **"It didn't work" means it didn't work.** Do not ask the user to try again, do not explain it as
   "you may not have noticed". The only conclusion is that you did not find the consumption point.
2. **Do not read assembly to pick a site.** No capstone loops, no manual offset math, no hand-built
   patches. Use the engine's three read-only ops: `near` / `refs` / `explain`.
3. **Change one site at a time.** Read it back immediately, and hand over only the one thing the user
   can verify by eye.

Also: **land only a `site` returned by the current `ask`/`step`**; **never press `land` twice for the
same goal** (measured: 540 -> 1080).

---

## Context discipline

Hand-reading assembly eats context; halfway through, the model starts flipping hypotheses and
treating one offset as truth.

1. At most **one function, first 40 instructions**, then stop.
2. **3 rounds** without a conclusion -> stop. Switch `ask kind=<another gate>`, add an organ, or say
   "cannot do it, missing X".
3. No full-disassembly scans. Use `near` / `refs` / `explain`, or let `ask` scan.
4. No raw hex "confirmation". Confirm with `land` + independent read-back, or in game.
5. Past half context: wrap up, write a handoff, start a new session.

---

## Entry points

```bash
export PYTHONIOENCODING=utf-8          # Windows: without this, Chinese output can crash on GBK

# one-shot (recommended): dry run by default, --write lands candidate #1
python niliu.py change "D:/games/x.exe" 150 75
python niliu.py change "D:/games/x.exe" 150 75 --write

# advanced: pick sites yourself / read full receipts
python niliu.py serve                  # hello line, then one JSON in / one JSON out
python niliu.py task examples/02_table_column.json
```

`change` is `start -> ask -> land`; every guard applies. `--kind`, `--width`, `--top` override defaults.

---

## Standard flow (8 steps)

```
0 close game      -> land writes the exe on disk
1 probe           -> python tools/survey.py <exe>, or read profile/presets from start
2 state the goal  -> start{exe,from,to,width,name}; always set width
3 choose a gate   -> ask{kind:"auto"} first, then an explicit kind if ranking is wrong
4 read receipt    -> site / va / site_width / score / evidence / n
5 cross-check     -> explain + near + refs; pin one (base,disp)
6 land one site   -> land{site,to,width}; success means readback == to
7 verify in game  -> restart, look at that one thing
8 archive/rollback-> map export; restore with the printed cp -f command
```

### Field rules

| Field | Rule |
|---|---|
| `from` | the value in the file on disk, not the in-game display. `from = 0` is rejected |
| `to` | new value; must fit in `width` |
| `width` | **always set it.** When omitted: `from > 0xFFFF ? 4 : 1`; `from=100` becomes 1 byte and only the low byte is patched; `to > 255` then fails |
| `name` | label stored in the archive, used by `archive.recall` |

`site_width` in the receipt is the byte width the site needs; when a data site has no constant entry
it falls back to `goal.width` — compare it with `evidence` before landing.

---

## Protocol (22 ops, exactly what `help` returns)

### Main flow (12)

| op | required | optional | purpose |
|---|---|---|---|
| `help` | — | — | ops, gates, organs, windows. **First call of any session** |
| `start` | `exe`,`from` | `to`,`width`,`name` | build map (~20-30 s first time, then cached), probe, recall archive |
| `ask` | — | `kind`,`top`,`budget_s`,`window`,`from`,`to`,`width` | one query, returns ranked sites |
| `step` | — | `n` (<=20) | GEDA fires n rounds and keeps score |
| `techs` | — | — | technique weights and hit rates (no start needed) |
| `state` | — | — | round, elapsed, genes, experience pool |
| `land` | `site`,`to` | `width` | backup -> write -> independent read-back -> archive |
| `map` | — | `out` or `q` | export map book / search landed sites by name |
| `near` | `va` | `n`,`exe` | read-only: instructions from an address |
| `refs` | `va` | `exe` | read-only: who calls/jumps to it |
| `explain` | `site` | `exe` | read-only: full checkup of a site |
| `stop` | — | — | close |

### Live memory, read-only (10)

Run `live_attach{exe:"name.exe"}` first; the rest depend on it.

| op | required | optional | purpose |
|---|---|---|---|
| `live_attach` | `exe` | — | read-only handle; returns pid/module/base/size |
| `live_scan` | `value` | `width`(4),`max`(40),`heap`(true) | addresses currently equal to value |
| `live_snap` | — | — | snapshot, returns snap id (keeps last 3) |
| `live_diff` | — | `snap`,`max`(60),`align`(4) | which 4-byte words changed -> counters |
| `live_read` | `addr` | `n`(64) | hex + i32 |
| `live_chain` | `addr`,`offsets` | — | pointer chain: deref root, read pointers, last offset is the final displacement |
| `live_rect` | `x`,`y` | `span`(24),`max`(30) | which widget rectangle contains the point |
| `live_rects_page` | — | `min_area`(600),`max_area`(60000),`max`(60) | button-like rectangles on this page |
| `live_widgets` | `addr` | `n`(8),`stride`(0x60) | follow the widget chain |
| `live_watch` | `keys` | — | named values: `{"sun":"0x16f97010+0x5560"}` |

Live ops locate objects, verify values and find buttons. **Patching still goes through `ask -> land`
on disk; live memory is never written.**

---

## Gates (`ask.kind`)

`auto` runs only the first five: `record -> imm -> arm -> typed -> f32`.
The other five must be named explicitly.

| kind | accepts when | typical target | `from/to` |
|---|---|---|---|
| `record` | value sits in one column of a name-anchored table: >=3 rows, common divisor, not a filler, lone votes yield | cost table, cooldown table | original -> new |
| `imm` | `mov [obj+disp], imm`: base not stack, `disp<=0x1000`, independent read-back | single constant (4000/1500/200) | the immediate |
| `arm` | value is another arm of the same `cmp reg,k` switch | typed constants (sun 25 -> 50) | one arm |
| `typed` | value is some bytes of an f64, both sides still look sane | 400.0 -> 100.0 | **byte values** 121 -> 89, `width:1` |
| `f32` | some byte of a 4-byte float, constant referenced from `.text` | 0.23 -> 0.46 | **byte values**, `width:1` |
| `addimm` | `add/sub [obj+disp], imm`: destination not stack, `disp<=0x1000`, 8-bit immediate signed | 4 damage per bite | decrement per event |
| `idtable` | anonymous type table: value in `.data/.rdata` followed by a `1,2,3...` id column, >=6 rows, stride 8-48 | `damage[type]` / `hp[type]` | any cell |
| `typedref` | referenced f64 multiplier: 8-byte aligned, <=3 decimals, `|v|<=1000` | 0.4 -> 0.1 | **byte values** 217 -> 185 |
| `incdec` | `inc/dec [obj+disp]`, ModRM reg bits verified, destination not stack | per-frame counter | increment per frame |
| `dataval` | bare variable: `.data/.rdata` + absolute reference from `.text` | `int g_hp = 100;` | original -> new, `width:4/8` |

Organs (evidence only, never ranking): `typed` `f32` `field` `addfield` `idtable` `f64ref`
`incdec` `dataval` `record` `store` `reg` `lea` `data`.

Ranking is GEDA only (`CLUE + dyn_weight + boost`, weighted roulette); `step` feeds results back.

---

## Reading a receipt

```json
{"ok":true,"gate":"typed","window":48,"n":1,"site_width":1,
 "rows":[{"site":"0x2793de","va":"0x6793de","text":"f64 @0x2793d8 byte 6",
          "score":12.0,"evidence":{"gate":"typed","f64":[400.0,100.0],"byte":6,"ratio":0.25}}]}

{"ok":true,"site":"0x2793de","width":1,"from":121,"to":89,"readback":89,
 "backup":"var/backups/x.exe.ec46d6b244c2.bak","archive":"20261017_223534_demo",
 "rollback":"cp -f \"var/backups/...bak\" \"D:/games/x.exe\""}
```

- `site` is a **file offset** (VA is also accepted; the engine subtracts the base). `va` is for
  `near/refs/explain`.
- Equal-score rows: do not pick by order. Compare `evidence`: table name / `votes` / `gcd` >
  pure producer vs accumulator > arm set > reference evidence > location sanity.
- Success is `readback == to` (the read-back reopens the file; it is not a cache).

---

## Landing and rollback

```
land -> var/backups/<exe>.<md5[:12]>.bak
     -> write + fsync
     -> reopen and read back independently
     -> var/archives/<time>_<name>.json
```

Rollback = copy the `.bak` back. On Windows do **not** rely on the `copy` in the receipt
(measured: silent no-op under cygwin); use:

```bash
cp -f "var/backups/x.exe.ec46d6b244c2.bak" "D:/games/x.exe"
```

Guards: the site must come from the current `seen` set (**`seen` is empty on a cold start — never
`land` before `ask`**); already at target -> refuse; does not fit width -> refuse; file locked ->
refuse; after writing, independent read-back.

---

## Failure diagnosis (when the user says "nothing changed")

1. **Confirm the code runs in the target scenario.** Not executed = wrong place, not wrong method.
2. **"Mod N" had no effect -> look at who writes the counter.** If the caller enters once every N
   frames, modulo N is always true.
3. **`cmp [obj+disp],0` -> check for `dec/inc` first.** No increment/decrement point = state flag,
   not a timer.
4. **One value may have three chains** (state flag / modulo gate / counter). Pin it with
   "same base + same displacement"; one chain alone is a guess.

---

## Verification (run after any engine change)

```bash
python tools/guard.py              # 12 structural guards, must be all green
python core/exam.py <pvz.exe> 30   # 18 papers
python tests/generality.py         # synthetic C target, no game needed
```

Measured 2026-10-23:

```
guards 12/12 green (13 organs, 13 presets, 4 ready / 5 gaps)
exam 14/18, mean F1 0.778
generality 4/6 (tables ok, floats ok, switch constants not found)
```

**These are floors, not graduation.** Graduation: exam 18/18 **and** generality 6/6.

---

## Limits (say so plainly)

- **Jump-table switches** (gcc/clang/MSVC 2015+): `gate_jt` missing; `arm` only walks `cmp` chains.
- **Virtual calls / object identity**: `prov` missing; cannot tell the same `disp` on two objects.
- **i16 / i8 constants**: only f64 / f32 byte patching exists.
- **Unity IL2CPP / Mono / ARM64 / ELF**: PE + x86/x64 only.
- **Live memory writes**: `live_*` is read-only; patching goes through disk.
- **No restart-free patching**; no guarantee the field is consumed.
- **Boss / special modes**: not auto-detected; pass the type value or cap it.
- **`from = 0`** is rejected.
- **x64 `explain`**: VA/FO conversion assumes `0x400000`; on 64-bit use `near/refs` with VA.

---

## Worked example: PvZ 1.0.0.1051 EN (32-bit native)

| Item | Value |
|---|---|
| bits / linker | 32-bit x86 / 8.0 (VS2005) |
| timestamp | 2009-04-21 06:21 (`1240266083`) |
| Rich header | absent (stripped); static CRT, 10 Win32 DLLs |
| size | `.text` 0x251000; 761389 instructions; 252829 constants; 285491 field writes |
| shapes | cmp chains 20423, jump tables **0**, `jmp reg` 55 (virtual calls), scaled 5944, field writes 72732, floats 17412, name tables 23 |
| base / code | `0x400000` / `.text 0x401000..0x652000` |
| zombie init | `0x522580` |
| HP field | `+0xc8`; armor `+0xd0` / `+0xdc` |
| HP values | 270/450/500/850/1350/3000; armor 100/300/370/1100/1400/2200 |
| Boss | type `0x20`, HP 6000 |
| sun | counter `board+0x5560` (cap 9990); production `0x4309D0` (4/5/6 -> 25/15/50) |
| conveyor period | f64: `0x679628` / `0x6795E0` / `0x6798A0` / `0x6793D8` |
| GameMode | `+0x7f8`; bowling = 35 |
| bite damage | `0x12FCF0`: `add dword ptr [esi+0x40], -4` (`addimm`) |

> Offsets are for this exact build only. Another build shifts everything.

---

## Pitfalls (all measured)

| Date | Symptom | Cause | Fix |
|---|---|---|---|
| 10-17 | `invalid choice` | v1 syntax with `native` | v3 only has `change`/`serve`/`task` |
| 10-17 | patched but nothing changed | write failure treated as success | `land` has built-in independent read-back |
| 10-17 | HP became 4x | same job pressed `land` twice | restore backup, replay once |
| 10-17 | `PermissionError` | game locks the exe | close the game |
| 10-17 | GBK crash on Chinese output | encoding not set | `PYTHONIOENCODING=utf-8` |
| 10-17 | two same-name exes shared a map | cache key was name + size | now includes md5 |
| 10-17 | `cmd //c copy` rollback did nothing | cygwin escaping fails silently | use `cp -f` |
| 10-17 | target 400.0 not found | `const double` folded by `-O1` | add `volatile` to the target |
| 10-17 | gcc switch not found | jump table | known gap, do not fight it |
| 10-18 | dozens of manual assembly reads, all wrong sites | context saturation -> flipping hypotheses | stop after 3 rounds |
| 10-18 | single constant not found by `auto` | `auto` covers only five gates | name the gate |
| 10-18 | treated `call 0x5317C0` as a file offset | it is a VA | subtract the base |
| 10-23 | only the low byte changed | width guessed from `from` | always set `width` (`change` copies `site_width`) |
| 10-23 | cold-start `land` was not blocked | `seen` empty disables site validation | always `ask` first |
| 10-23 | one more 80 MB cache per run | cache key includes md5 | expected; clean `var/` when large |
| 10-23 | `explain` wrong on x64 | VA/FO assumes `0x400000` | use `near/refs` on 64-bit |
| 10-23 | "probably not MSVC" from a missing Rich header | absence only means it may be stripped | check the linker version |

---

## One line

> **You give `from -> to`; the engine gives a few evidence-backed sites; you land one and it backs up,
> reads back and hands you a rollback.**
> When it refuses, do not go around it — read which gate said no and which shape is missing.
