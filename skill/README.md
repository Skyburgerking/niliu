# skill/ — installable Agent Skill

This folder **is** the skill `niliu-injection-engine` (the folder name must match the `name` in
`SKILL.md` when installed).

| File | Language | Purpose |
|---|---|---|
| `SKILL.md` | English | execution card: prerequisites, rules, 22 ops, 10 gates, pitfalls |
| `SKILL.zh-CN.md` | 中文 | same card in Chinese |

---

## Install

The skill needs the engine next to it, so clone this repository first, then link/copy the folder:

```bash
git clone https://github.com/Skyburgerking/niliu.git
cp -r niliu/skill ~/.claude/skills/niliu-injection-engine      # Claude Code style
cp -r niliu/skill ~/.deepcode/skills/niliu-injection-engine     # DeepCode style
```

Windows PowerShell:

```powershell
git clone https://github.com/Skyburgerking/niliu.git
Copy-Item -Recurse niliu\skill "$env:USERPROFILE\.claude\skills\niliu-injection-engine"
```

Keep the cloned `niliu` folder: the card tells the agent to run `python niliu.py ...` from that
directory. Updating the engine (`git pull`) updates the skill card at the same time.

---

## Prerequisites

1. **An LLM agent with tool use** — this card is written to be loaded by a model, not read as a
   hand-patching manual.
2. Python 3.10+, `capstone>=5.0`, Windows, PE x86/x64 target.
3. A single-player game you own, for personal use and study. No online or competitive cheating.

---

## Use

Load the skill, then talk to the agent in goals:

```
"change the sun cost in this game from 50 to 25"
```

The agent runs `python niliu.py change <exe> 50 25` (dry run), shows the candidates with their
evidence, and only writes after you confirm.

---

## One line

> The model states `from -> to`; the engine returns evidence-backed sites; landing one gives a
> verified patch and a rollback command.
