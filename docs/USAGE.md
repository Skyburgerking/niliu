# niliu — usage

> The engine is the only thing that picks sites. You supply `from -> to`; you never supply an address.

---

## 0. Install

```bash
pip install -r requirements.txt     # capstone
python tools/survey.py "D:/games/x.exe"   # optional: inspect the binary first
```

Windows notes: set `PYTHONIOENCODING=utf-8` in the shell, otherwise Chinese console output can
crash with a GBK codec error. Close the game before patching: a running process locks the exe.

---

## 1. Three entry points

```bash
# A. one-shot (recommended)
python niliu.py change "D:/games/x.exe" 150 75            # dry run
python niliu.py change "D:/games/x.exe" 150 75 --write    # land candidate #1

# B. resident process, one JSON in / one JSON out
python niliu.py serve

# C. batch jobs
python niliu.py task examples/02_table_column.json
```

`change` is a thin wrapper over `start -> ask -> land`; every guard still applies.

---

## 2. The 8-step loop

```
0  close the game          patching writes the file on disk
1  probe                   python tools/survey.py <exe>, or read profile/presets from start
2  state the goal          start{exe,from,to,width,name}; always set width explicitly
3  choose a gate           ask{kind:"auto"} first, then an explicit kind if the ranking is wrong
4  read the receipt        site / va / site_width / score / evidence / n
5  cross-check             explain + near + refs; pin one (base,disp)
6  land one site           land{site,to,width}; success means read-back == to
7  verify in game          restart, look at that one thing
8  archive / rollback      map export; restore with the printed cp -f command
```

### Field rules

| Field | Rule |
|---|---|
| `from` | the value in the file on disk, **not** the value currently shown in game. `from = 0` is rejected |
| `to` | new value; it must fit in `width` |
| `width` | **always set it.** When omitted the engine guesses `from > 0xFFFF ? 4 : 1`, so `from=100` becomes 1 byte and only the low byte is patched; `to > 255` then fails with "does not fit" |
| `name` | label stored in the archive, so `archive.recall` can find it later |

`start` returns `goal.width`, `presets.ready/gaps` and `archive.recall` (what was landed for this
target before, if anything).

---

## 3. Ops (22)

| Op | Purpose |
|---|---|
| `help` | list ops, gates, organs, window sizes, `ask` kinds |
| `start` | open an exe, build/lookup the map, probe, recall the archive |
| `ask` | run one gate (or `auto` = the first five) and return ranked sites |
| `step` | advance `n` rounds of GEDA search (keeps the seen set) |
| `state` | current goal, counts, last evidence |
| `techs` | technique weights and their measured hit rates |
| `land` | patch one site: backup, write, independent read-back, archive, rollback cmd |
| `map` | export the known sites of this exe |
| `near` | list instructions around a file offset (read-only) |
| `refs` | list code references to a VA (read-only) |
| `explain` | explain one address: section, VA/FO, neighbours (read-only) |
| `stop` | close the resident process |
| `live_attach` | attach to a running process (read-only) |
| `live_scan` | scan live memory for a value |
| `live_snap` | snapshot a range |
| `live_diff` | diff two snapshots |
| `live_read` | read live memory at an address |
| `live_chain` | follow a pointer chain |
| `live_rect` | read one widget rectangle |
| `live_rects_page` | page through widget rectangles |
| `live_widgets` | enumerate widgets |
| `live_watch` | watch a value over time |

All `live_*` ops are **read-only**; patching still goes through disk.

---

## 4. Gates (10)

| Gate | Finds | Typical target |
|---|---|---|
| `record` | name-anchored struct tables (stride, column, gcd, placeholders) | price / HP column |
| `imm` | `mov [obj+disp], imm` | one constant field |
| `arm` | `cmp reg,k` chains, another arm of the same switch | typed initial values |
| `typed` | f64 constants, byte substitution | 400.0 -> 100.0 |
| `f32` | f32 constants | 0.23 -> 0.46 |
| `addimm` | `add/sub [obj+disp], imm` | damage per bite |
| `idtable` | value column + incrementing id column | `damage[type]` |
| `typedref` | f64 multiplier referenced by code | 0.4 -> 0.1 |
| `incdec` | `inc/dec [obj+disp]` | cooldown counter |
| `dataval` | bare global addressed by absolute reference | `int g_hp = 100;` |

`auto` only runs the first five (`record`, `imm`, `arm`, `typed`, `f32`). For the other five, name the
gate explicitly.

---

## 5. Recipes

### 5.1 A column in a named table (cost / HP)

```bash
python niliu.py change "D:/games/x.exe" 150 75 --kind record
```

The same value appears in every row; the engine votes on stride x column offset. Each row is a
separate site, so land them one at a time (or patch the whole column with a small script once the
offset is confirmed).

### 5.2 A switch-case constant

```bash
python niliu.py change "D:/games/x.exe" 25 50 --kind auto
```

Needs a `cmp reg,k` chain next to the store; gcc-style jump tables are not covered (`gate_jt` missing).

### 5.3 An f64 constant

```bash
python niliu.py change "D:/games/x.exe" 121 89 --kind typed --width 1
```

`121` is the 6th byte of `400.0`, `89` is the 6th byte of `100.0`. Patch only the byte that differs.

### 5.4 A global variable

```bash
python niliu.py change "D:/games/x.exe" 100 200 --kind dataval
```

Works when the address is referenced by absolute immediates (32-bit code, non-PIE).

---

## 6. Reading a receipt

```json
{"ok": true, "gate": "arm", "n": 4,
 "sites": [{"site": 0x309f0, "va": 0x4309f0, "site_width": 4,
            "score": 14.0, "evidence": {"gate": "arm"}}]}
```

| Field | Meaning |
|---|---|
| `ok` | false means no candidate passed; `err` says why |
| `site` | file offset to patch (what `land` expects) |
| `va` | virtual address (for `near` / `refs`) |
| `site_width` | bytes this site needs; `--width` overrides only when you know better |
| `score` | GEDA score, higher is better; it is a ranking, not a probability |
| `evidence` | why the gate accepted it |
| `n` | number of candidates returned |

---

## 7. Failure diagnosis

| Symptom | Likely cause | Fix |
|---|---|---|
| `no site` / every gate says "not my question" | wrong gate for this shape | try `record`, `imm`, `addimm`, `idtable`, `dataval` |
| candidate list empty for a table | the table has no name anchors | use `imm` on one row, or `typed` for floats |
| `site ... was not returned by ask/step` | cold start, `land` without `ask` | always `ask` first |
| `already 89 there, nothing changed` | the file is patched | restore the backup, or pick another value |
| `300 does not fit in 1 byte` | `width` guessed as 1 | pass `--width 4` |
| `PermissionError` | game is running | close it |
| game starts but nothing changes | this field is not consumed | try another candidate; do not patch the same site twice |
| same game, one more 80 MB cache per run | cache key includes md5 | delete `var/*.pkl` when it gets big |

---

## 8. Landing and rollback

`land` does all of this in one op:

1. copy the original to `var/backups/<name>.<md5[:12]>.bak`
2. write the new bytes
3. read the bytes back from disk, independently
4. append an archive entry under `var/archives/`
5. print a `cp -f` rollback command

If read-back does not equal `to`, the op fails and the file is left untouched.

Never press `land` twice for the same goal: the second patch would apply the new value to the
already-patched file and can double the effect.

---

## 9. Extending

1. add an organ in its own file, decorate with `@R.organ("name", ["gate"], "description")`
2. add a gate in `core/hunt.py` (`R.gate` registration) or reuse an existing one
3. add thresholds to `rules/rules.json` (never hard-code numbers)
4. add a row to `rules/presets.json` if the shape is common
5. run `python tools/guard.py` and `python core/exam.py <exe> 30`

---

## 10. Limits

- PE / x86 / x64 only. No ELF, ARM64, Unity IL2CPP, Mono.
- Jump-table switches, virtual calls and object identity are not implemented (`gate_jt`, `prov`).
- Only f64 / f32 byte patching; no i16 / i8.
- `live_*` is read-only.
- No restart-free patching, no guarantee the field is consumed.
