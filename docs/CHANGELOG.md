# Changelog

All numbers below were measured on the date shown. They are floors: a change that lowers them is a
regression.

## 2026-10-23 — release layout, one-shot entry

- added `python niliu.py change <exe> <from> <to> [--write]`: `start -> ask -> land` behind one
  command; dry run by default, lands only the first candidate, copies `site_width`
- release copy reorganised: engine in `core/`, thresholds in `rules/`, runtime output in `var/`
- comments and docstrings in the release copy are English; the development tree stays Chinese
- fixed: map cache directory is created on demand (a fresh clone no longer needs `var/` to exist)
- baseline: guards 12/12, exam 14/18 (F1 0.778), generality 4/6

## 2026-10-20 — read-only live memory

- added 10 `live_*` ops: attach, scan, snapshot, diff, read, pointer chain, widget rects, widget
  enumeration, watch
- all of them read-only by design; patching still goes through disk

## 2026-10-18 — gates and GEDA

- gate count reached 10: record, imm, arm, typed, f32, addimm, idtable, typedref, incdec, dataval
- GEDA ranks accepted sites with measured per-technique hit rates
- exam harness added (18 papers, precision/recall/F1)

## 2026-10-17 — v3

- engine rewritten as a JSON protocol: `serve` (line-JSON) and `task` (batch jobs)
- organs self-register; the main pipeline no longer contains organ names
- `land` became a transaction: backup, write, independent read-back, archive, rollback command
- removed the old `native` subcommand from v1

## Known gaps

- `gate_jt` (jump-table switches) and `prov` (object identity / virtual calls) are not implemented
- only f64 / f32 byte patching; no i16 / i8
- PE + x86/x64 only; no ELF, ARM64, Unity IL2CPP, Mono
- `from = 0` is rejected
