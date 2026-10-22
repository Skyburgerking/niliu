# 逆流 niliu

**给一个模糊要求（`from` → `to`），它回几处带证据的站点；落一处，它备份、回读、给回滚命令。**

`niliu`（逆流）是给单机游戏做二进制改值的引擎。它不要求你读汇编，也不许你猜地址：
你说磁盘上的原值和想要的新值，它给你一张很短的候选表，每个候选都带着"凭什么过门"的证据。

```
python niliu.py change "E:/games/PlantsVsZombies.exe" 25 50
```

```
逆流 change   25 → 50
  exe     E:\games\PlantsVsZombies.exe
  摸底    32-bit x86 / 原生 Win32 / cmp链 20423 / 跳表 0 / 名字表 23 / 浮点 17412
  能打    分档常量、名字锚定结构表、指针推进式遍历、f64 常量
  缺口    虚调用（prov）、对象初始化串、f32、i32/i16/i8、字符串哈希分派

判据 arm   候选 4 条   3.49 s
  #   站点         宽   分     说明
  1   0x309f0      4    14.0   mov ecx, 0x19
  2   0x1b9b8      4    13.5   mov eax, 0x19
  3   0x5855d      4    13.0   mov dword ptr [esi + 0x20], 0x19
  4   0x329a9      4    12.0   mov eax, 0x19

未改文件。确认后加 --write 落第 1 条。
```

> 2026-10-23 在 PvZ 1.0.0.1051 原件上真跑的输出。

---

## 30 秒上手

```bash
# 1. 依赖只有一个
pip install -r requirements.txt

# 2. 看候选（不改任何字节）
python niliu.py change "D:/games/x.exe" 150 75

# 3. 落第 1 条（备份 → 写 → 独立回读 → 档案 → 回滚命令）
python niliu.py change "D:/games/x.exe" 150 75 --write

# 4. 重启游戏，只看这一处
```

| 参数 | 说明 |
|---|---|
| `--write` | 真的落盘；不加就只看 |
| `--width N` | 强制字节宽度；默认听引擎回执里的 `site_width` |
| `--kind K` | `auto`（默认）/ `record` / `imm` / `arm` / `typed` / `f32` / `addimm` / `idtable` / `typedref` / `incdec` / `dataval` |
| `--top N` | 显示几条候选（默认 8） |
| `--json` | 只吐一行原始 JSON |

护栏不变：默认只看不写、只落第 1 条、`readback == to` 才算成、同一目标不连按两次。

---

## 它现在能找什么

| 目标 | 判据 | 例子 |
|---|---|---|
| 名字结构表里的一列（价格/血量） | `record` | 花费 150 → 75 |
| 分档初值 / switch 常量 | `arm` | 阳光 25 → 50 |
| 单个 `mov [obj+disp], imm` | `imm` | 咀嚼 4000、射速 200 |
| 每次事件扣减的常量 | `addimm` | 僵尸每口 4 点血 |
| 每帧 −1 的计数器 | `incdec` | 冷却倒计时 |
| 匿名类型表（值列 + 递增 id） | `idtable` | `damage[type]` / `hp[type]` |
| f64 常量（改一个字节） | `typed` | 400.0 → 100.0 |
| 被引用的 f64 倍率 | `typedref` | 0.4 → 0.1 |
| f32 常量 | `f32` | 0.23 → 0.46 |
| C 风格全局变量 | `dataval` | `int g_hp = 100;` |

排序只由 GEDA 做（加权轮盘 + 实测反馈），器官只负责填证据。
摸底会告诉你这游戏「能打哪几类、缺哪几类」，`presets.gaps` 里的形态就是做不了的，别硬碰。

---

## 工作原理

```
目标 {from, to, width}
   |
   v
器官  ...  找候选 + 证据                    （13 个器官）
   |
   v
判据  ...  放行或拒绝                       （10 条判据）
   |
   v
GEDA  ...  给通过的站点排序，学哪条技术有用   （加权轮盘 + 奖励）
   |
   v
落盘  ...  备份 → 写 → 独立回读 → 档案 → 回滚命令
```

- 器官是**注册**进去的（`registry.py` + `@R.organ`），主流程不写死名单。
- 判据是契约；答不了的判据会明说"我不回答这个"。
- 每一处落盘都带改前 md5 进档案，`--restore` 和 `cp -f` 都能回滚。

---

## 目录

```
niliu.py            唯一入口：change / serve / task
core/               引擎（25 个模块）
  hunt.py           主流程：recon → enum → rank → refine
  geda.py           加权轮盘、技术权重、奖励池
  map.py            PE 解析 + 反汇编 + 索引
  registry.py       器官 / 判据自注册表
  typed.py …        器官模块（共 13 个器官）
  inspect_ops.py    near / refs / explain（只读）
  live_ops.py       活内存只读
  archive.py        每个 exe 的档案：结构 + 目标履历
  profile.py        摸底 → 选预设 → 能打/缺口
  exam.py           18 张卷的考试
  replay.py         按清单复刻
rules/              rules.json（参数总闸）、presets.json（13 条形态）
docs/               用法、设计、技能卡、变更记录
examples/           三个 job 示例，改个路径就能跑
tools/              guard.py（12 条守卫）、survey.py（单独摸底）
tests/              generality.py + 合成 C 靶场与预编译靶子
facts/              PvZ 考前真值
var/                运行产物（备份 / 档案 / 建图缓存），已进 .gitignore
```

运行产物只写 `var/`，规则只读 `rules/`，不往项目外写。

---

## 文档

| 文件 | 给谁看 |
|---|---|
| [docs/USAGE.zh-CN.md](docs/USAGE.zh-CN.md) | 中文完整用法（22 个 op、10 条判据、失败诊断） |
| [docs/USAGE.md](docs/USAGE.md) | English version of the same workflow |
| [docs/DESIGN.md](docs/DESIGN.md) | 为什么这么设计 |
| [docs/SKILL.md](docs/SKILL.md) | 给 LLM 的精简执行卡 |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 实测能力变化 |

---

## 验收

```bash
python tools/guard.py              # 12 条结构守卫
python core/exam.py <pvz.exe> 30   # 18 张卷（需要 PvZ 1.0.0.1051 原件）
python tests/generality.py         # 合成 C 靶场（需要 gcc 与 x86_64-w64-mingw32-gcc）
```

2026-10-23 实测：

```
守卫      12/12 绿
考试      14/18 满分，平均 F1 0.778
通用性     4/6（表列 ✓✓ 浮点 ✓✓ 分档 ✗✗）
```

**这是不许退化的底线，不是毕业。** 毕业线是考试 18/18 且通用性 6/6。

---

## 边界

- **跳表 switch**（gcc / clang / MSVC2015+）：`gate_jt` 未实现，`arm` 只认 `cmp` 链。
- **虚调用 / 对象身份**：`prov` 未做，分不清同一 `disp` 在不同对象上。
- **i16 / i8 常量**：只做了 f64 / f32 的逐字节改。
- **Unity IL2CPP / Mono / ARM64 / ELF**：只认 PE + x86/x64。
- **活内存改值**：`live_*` 只读；改值仍走磁盘。
- **不重启就生效**：做不到。
- **保证改了有效果**：做不到，有的字段没人读。
- **`from = 0`**：不支持（按"没给"处理）。

---

## 许可

MIT，见 [LICENSE](LICENSE)。可自由使用、修改、再分发、商用，保留版权声明即可。

> **一句话：** 你给 `from → to`，它给几处带证据的站点；你落一处，它备份 + 回读 + 给回滚。
