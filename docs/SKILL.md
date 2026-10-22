# niliu — skill card (for an LLM agent)

> One rule above all: **you do not write reverse-engineering code, you emit JSON and the engine works.**
> You never supply an address. You supply `from -> to`.

---

## Three hard rules

1. **Never hand-pick a site.** Use `ask` / `step`. If no gate answers, say which gate and which shape
   is missing — do not fall back to reading assembly yourself.
2. **Three rounds without a conclusion means stop.** Switch gate, add evidence, or say "cannot do it,
   missing X".
3. **Never land twice for the same goal.** A second `land` patches the already-patched file.

---

## Entry

```bash
python niliu.py change <exe> <from> <to> [--write] [--kind K] [--width N]
python niliu.py serve                 # line-JSON in / out
python niliu.py task job.json         # {"ops": [...]}
```

---

## Flow

```
close the game -> survey -> start{exe,from,to,width,name}
  -> ask{kind:"auto"} -> read sites/score/evidence
  -> cross-check with explain/near/refs
  -> land{site,to,width} -> read-back == to
  -> verify in game
```

Always set `width`. When omitted, the engine guesses `from > 0xFFFF ? 4 : 1`.

---

## Gates

| Gate | Use for |
|---|---|
| `record` | column in a named struct table |
| `imm` | one `mov [obj+disp], imm` |
| `arm` | switch-case / typed initial value |
| `typed` | f64 constant, byte substitution |
| `f32` | f32 constant |
| `addimm` | per-event decrement |
| `idtable` | anonymous type table |
| `typedref` | referenced f64 multiplier |
| `incdec` | counter |
| `dataval` | bare global |

`auto` = `record`, `imm`, `arm`, `typed`, `f32` only.

---

## Receipt

```json
{"ok": true, "gate": "record", "n": 17,
 "sites": [{"site": 0x29f4dc, "va": 0x69f4dc, "site_width": 1,
            "score": 18.0, "evidence": {"gate": "record"}}]}
```

`ok:false` + `err` means no candidate passed. Read `err` before changing anything.

---

## Landing

`land` = backup -> write -> independent read-back -> archive -> rollback command.
Success is `readback == to`. If not, the file is untouched.

---

## Do not

- do not scan the whole disassembly by hand;
- do not trust "looks right";
- do not patch the same site twice;
- do not promise an effect you have not seen in game;
- do not fight shapes in `presets.gaps`.

---

## Known gaps

- jump-table switches (`gate_jt`)
- virtual calls / object identity (`prov`)
- i16 / i8
- Unity IL2CPP / Mono / ARM64 / ELF
- `from = 0` unsupported
