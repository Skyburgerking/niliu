# tools

Two standalone tools. Both are read-only unless stated otherwise.

| Tool | Purpose |
|---|---|
| `guard.py` | 12 structural guards. Must be all green before any change lands. |
| `survey.py` | Probe one exe: PE header, Rich header, sections, imports, instruction shapes. |

```bash
python tools/guard.py
python tools/survey.py "D:/games/x.exe"
```

`guard.py` covers: rules completeness, organ self-registration, no organ names in the main
pipeline, file size limit, every rule is actually read, gate contracts, no output under
`C:\cygwin64`, independent read-back in `land`, organ smoke test, meta-test (guards can go red),
generality target, preset library.

`survey.py` prints: PE header (bits, subsystem, linker version, timestamp, sections), Rich header,
debug directory (PDB/GUID), imports, mnemonic distribution, and shape probes (switch chains,
jump tables, name tables, field writes, float constants, indirect calls).
