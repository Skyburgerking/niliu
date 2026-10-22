# Examples

Three job files, one per common shape. **Change the `exe` path and run.** Nothing else needs editing.

```bash
python niliu.py task examples/01_switch_value.json
python niliu.py task examples/02_table_column.json
python niliu.py task examples/03_f64_byte.json
```

| File | Shape | What it does |
|---|---|---|
| `01_switch_value.json` | switch-case constants | 25 -> 50; `auto` reaches `arm` (another arm of the same `cmp reg,k` chain) |
| `02_table_column.json` | name-anchored table | 150 -> 75; `record` returns every row of the column as a separate site |
| `03_f64_byte.json` | f64 constant | `400.0 -> 100.0`; `from/to` are **byte values** 121 -> 89, only byte 6 changes |

## Reading output

`task` prints one JSON line per op. To read it as a human:

```bash
python niliu.py task examples/02_table_column.json > out.jsonl
```

Then inspect `sites`, `score` and `evidence` per line.

## Rules

- jobs contain only `start`, `ask` and `step` — **never `land`**. Landing needs a human look at the
  candidates, and one site per run.
- to actually patch, use `python niliu.py change ... --write`.
- a job that returns `ok:false` is not a bug in the job; `err` names the missing shape.
