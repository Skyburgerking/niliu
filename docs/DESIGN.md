# niliu — design

## 1. The problem

A single-player game keeps a value (HP, cost, cooldown) somewhere in the binary. The same number
appears dozens or hundreds of times: as a table column, as a switch-case constant, as a float, as a
loop bound. Picking the right one by reading assembly is slow, and for an LLM it is also unreliable:
the context fills up and every new hypothesis overwrites the last one.

niliu turns that into a search problem with evidence. You state a vague goal (`from -> to`); the
engine proposes a short list of sites, each carrying the reason it passed a gate. The human or agent
only chooses among a few ranked candidates.

## 2. Three kinds of evidence

Most real targets fall into one of three shapes:

| Shape | Evidence | Gate |
|---|---|---|
| A column in a struct table | many rows with the same value, one stride, one column offset | `record` |
| A constant in a switch | `cmp reg,k` chain, the same register in several arms | `arm` |
| A typed constant | an 8-byte double in `.rdata`, referenced by `movsd`/`fld` | `typed` |

The rest are variants: a single field write (`imm`), an arithmetic decrement (`addimm`), an
incrementing id column (`idtable`), a multiplier (`typedref`), a counter (`incdec`), a bare global
(`dataval`).

## 3. Organs and gates are separate

An **organ** answers "where could this value live?" and returns evidence. A **gate** answers "is this
evidence enough to accept?" and returns pass/fail plus a score.

```
organ  ->  evidence dict  ->  gate  ->  accepted site (score)
```

Keeping them separate buys three things:

- an organ can serve several gates (a table column is also a set of `imm` writes);
- a gate can be tested with synthetic evidence (guard 6 does exactly this);
- adding a shape does not touch the main pipeline.

Organs register themselves (`@R.organ`), gates register themselves (`R.gate`). `hunt.py` never
contains a list of organ names; guard 3 enforces this.

## 4. Ranking is GEDA's job

Multiple gates can accept different sites for the same goal. GEDA (weighted roulette over techniques
plus reward bookkeeping) decides the order, using measured hit rates per technique and per shape.
The gate score is a feature, not the final answer.

This matters because the correct answer is often *not* the highest-scoring one: a table column
produces dozens of equally valid sites, while the "right" one depends on what the game reads.

## 5. Patching is a transaction

`land` is the only op that writes. It does exactly five things:

1. copy the original to `var/backups/<name>.<md5[:12]>.bak`
2. write the new bytes at the site offset
3. read the same bytes back from disk in a separate call
4. append an archive record (site, width, original, new, pre-patch md5)
5. print a `cp -f` rollback command

If step 3 does not return `to`, the op fails. There is no "probably worked".

`land` also refuses a site that did not come from the current `ask`/`step` result. Cold-start
`land` is rejected on purpose.

## 6. Why not scan the whole binary?

A full disassembly is already built once per exe (cached by md5). After that, every question is an
index lookup: constants, field writes, compare chains, references. A full re-scan per goal would be
slower and would make the evidence harder to explain.

The rule for the agent is the same: do not read assembly by hand. Use `near`, `refs` and `explain`,
which are part of the engine.

## 7. Measured state (2026-10-23)

```
guards      12 / 12
exam        14 / 18 full marks, mean F1 0.778
generality   4 / 6
```

Known gaps:

- jump-table switches (`gate_jt`);
- object identity for virtual calls (`prov`);
- i16 / i8 widths;
- Unity IL2CPP / Mono / ARM64 / ELF.

The graduation line is exam 18/18 **and** generality 6/6. Until then, the numbers above are the
floor that must not regress.

## 8. Failure modes the design accepts

- The engine can return several valid sites and no way to tell which one the game reads.
- A gate can accept a site in dead code.
- A patch can be correct and still have no visible effect.
- A table column can be patched partially (one row) and look like a failure.

Each of these is reported honestly instead of being hidden behind a confidence number.
