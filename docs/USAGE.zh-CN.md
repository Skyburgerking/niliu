# 逆流 v3 · 使用手册（唯一入口）

> 更新：2026-10-23（按 10-23 实跑结果重写）
> 引擎目录：本仓库根目录
> 这份是**唯一的主线用法**。英文精简版见 `USAGE.md`，设计说明见 `DESIGN.md`。
>
> 一句话：**你给 `from → to`，引擎给几处带证据的站点；你落一处，它备份、回读、给回滚。**

---

## 〇、先记住这五条（违反任意一条，结果必错）

1. **不写逆向代码。** 你只吐 JSON。读汇编也只走引擎的只读口（`near` / `refs` / `explain`），
   不许自己 capstone 逐条扫。手查超过 3 轮没结论就停，换判据或承认缺口。
2. **一次只改一处。** 落完立刻回读、立刻进游戏验。三处一起改，用户说"没变"时你分不清是哪条错。
3. **落盘只认 `ask` / `step` 回过的 `site`。** 不许凭记忆、凭反汇编、凭上次的地址直接 `land`。
4. **同一 job 绝不连按两次 `land`。** 实测过一次 540 → 1080。
5. **用户说"没成"就是没成。** 不许解释成"可能你没注意到"，唯一结论是**没定位到消费点**，继续查。

另外三条来自耐心三查：**先读完、先原样跑、说完成前当场给数。**

---

## 一、启动与傻瓜入口

```bash
cd "路径/到/niliu"
export PYTHONIOENCODING=utf-8          # Windows 不加，中文必崩 GBK
```

**日常只需要这一条**（默认只看不写；确认后加 `--write` 才落盘）：

```bash
python niliu.py change "D:/games/x.exe" 150 75            # 只看候选
python niliu.py change "D:/games/x.exe" 150 75 --write    # 落第 1 条
```

它内部仍然走 `start → ask → land`，所以护栏一条不少。输出依次是：
摸底（位数/编译器/汇编形态）→ 能打与缺口 → 候选表（站点/宽度/分/证据）→
（`--write` 时）备份、档案、回滚命令。

可选参数：`--width N`（强制宽度）、`--kind imm|record|arm|typed|f32|addimm|idtable|typedref|incdec|dataval`、
`--top N`、`--name hp`、`--json`（只吐一行原始 JSON）。

需要自己挑站点、看完整回执时，才用常驻口：

```bash
python niliu.py serve                  # 常驻：一行 JSON 进、一行 JSON 出
```

第一行必回 `hello`，里面带**当前真实的 op 表**。开工先发一条 `{"op":"help"}`，
以它回的 `ops / gates / organs / windows` 为准 —— 本文档和它对不上时，以引擎为准。

健康自检（三条，每次改完引擎都跑）：

```bash
python tools/guard.py                                          # 12 条结构守卫
python core/exam.py "测试/PvZ_原件.exe.newniliu_bak_20261017_202317" 30   # 18 张卷
python tests/generality.py                                        # 合成靶场（不依赖游戏）
```

2026-10-23 实测基线（**这是不许退化的底线，不是毕业**）：

```
守卫      12/12 绿（13 个器官、13 条预设、能打 4 / 缺口 5）
考试      14/18 满分，平均 F1 0.778（33.5 s）
通用性     4/6（表列 ✓✓ 浮点 ✓✓ 分档 ✗✗ —— 跳表缺口）
毕业线     考试 18/18 且通用性 6/6，缺一条都不算
```

---

## 二、标准流程（八步，按顺序，不许跳）

### 第 0 步：关游戏

`land` 改的是**磁盘上的 exe**。游戏开着会锁文件，回执是
`exe 被占用（游戏开着），文件没动`。改完要重启游戏才生效。

顺手记一下原文件 md5（排查"是不是我改的"用）：

```bash
md5sum "D:/games/x.exe"
```

### 第 1 步：摸底（先了解敌人）

```bash
python tools/survey.py "D:/games/x.exe"
```

或者 `start` 之后看回执里的 `profile` 与 `presets`。读法：

| 摸底字段 | 含义 | 对应用法 |
|---|---|---|
| `arch` / `bits` | 32 位还是 64 位 | 决定操作数形态；x64 的 `explain` 有坑（见 §七） |
| `toolchain` / `linker` / `rich` | 什么编译器、有没有被抹 | VS2005 时代多是 `cmp` 链；gcc/clang 多是跳表 |
| `cmp_imm` 多、`jt = 0` | 分档走 iff 链 | `arm` 对路 |
| `jt > 0` | 跳表分派 | **缺口，别硬碰**（`gate_jt` 未做） |
| `jmp_reg` 多 | 多半是虚调用 | 缺口 `prov`，别硬碰 |
| `tables > 0` | 有名字锚定结构表 | `record` 对路 |
| `float_ops > 0` | 有浮点常量 | `typed` / `f32` / `typedref` 可能对路 |
| `field_w` 多 | 对象初始化串 | `imm` / `addimm` 可能对路 |

`presets.gaps` 里列出的形态 = **这一类活现在做不了**。要么换路，要么如实告诉用户。

### 第 2 步：写清目标（三个数必须对）

```json
{"op":"start","exe":"D:/games/x.exe","from":100,"to":200,"width":4,"name":"hp"}
```

| 字段 | 规矩 |
|---|---|
| `from` | **磁盘上 exe 里的原值**，不是游戏里当前显示的值。`from = 0` 现在不支持（代码按"没给"处理） |
| `to` | 新值。必须装得进 `width` |
| `width` | **永远显式写。** 不写时引擎按 `from > 0xFFFF ? 4 : 1` 猜：`from=100` 会被猜成 1 字节，目标本是 4 字节字段时就只改低 1 字节；`to > 255` 还会直接报"装不进 1 字节" |
| `name` | 目标名（`hp` / `sun` / `cooldown`），会进档案，方便回查 |

`start` 回执里重点看三样：`goal.width`（是不是你要的宽度）、`presets.ready/gaps`、
`archive.recall`（这个目标以前落过盘的话，会告诉你上次改了哪）。

### 第 3 步：选判据（先 auto，再逐个单试）

```json
{"op":"ask","kind":"auto","top":8}
```

`auto` 只跑五个主判据：`record → imm → arm → typed → f32`。
**这五个都不对路时，按目标形态显式换 `kind`**（见 §三判据表）：

```json
{"op":"ask","kind":"addimm"}      // 每口/每帧扣减
{"op":"ask","kind":"idtable"}     // 按类型索引的匿名表
{"op":"ask","kind":"typedref"}    // 被代码引用的 f64 倍率（0.4 / 0.25）
{"op":"ask","kind":"incdec"}      // inc/dec 计数器
{"op":"ask","kind":"dataval"}     // C 风格全局变量
```

一条经验：**单常量先 `imm`，扣减 `addimm`，按类型分 `idtable`，倍率 `typedref`，
计数器 `incdec`，裸变量 `dataval`。** 这五类 `auto` 不会自己选。

### 第 4 步：读回执（会不会用，全看这一步）

```json
{"ok":true,"gate":"typed","window":48,"n":1,"site_width":1,
 "rows":[{"site":"0x2793de","va":"0x6793de","text":"f64 @0x2793d8 第6字节",
          "score":12.0,"evidence":{"gate":"typed","f64":[400.0,100.0],"byte":6,"ratio":0.25}}]}
```

| 字段 | 怎么用 |
|---|---|
| `site` | **文件偏移**，落盘就抄它（也接受 VA，引擎会减基址） |
| `va` | 虚拟地址，`near/refs/explain` 用它 |
| `site_width` | 该改几字节。**落盘前和 `evidence` 对一遍**：数据站点没有常量条目时会回退成 `goal.width` |
| `rows[].score` | 排序分。同分多行时**不要按顺序挑**，看证据分辨 |
| `evidence` | "凭什么"。出问题原样贴出来，别自己复述 |
| `n` | 候选总数；`n` 大而 `top` 小，说明还有没看的 |

**多条候选怎么分**（顺序就是优先级）：

1. 有名字锚点的表列（`evidence.table_names`、`votes`、`gcd`）—— 用 `record` 的那条。
2. 纯生产者 vs 累加器（`evidence` 里 `acc/ahead/back`）—— 累加器是"加到现有总量上"，通常不是你要的初值。
3. 分档集（`evidence.arm` / `cmp_imm`）—— 同一个 `cmp reg,k` 的另一档。
4. 引用证据（`evidence.refs` / `consumer`）—— 被代码引用的比没人读的可信。
5. 位置常识：`disp ≤ 0x1000`、基址不是 `esp/ebp`（栈帧不算对象字段）。

### 第 5 步：交叉验证（落盘前必须做一次）

三个只读口，全是引擎自己算，不需要你写反汇编：

```json
{"op":"explain","site":"0x2793de"}
{"op":"near","va":"0x6793d8","n":12}
{"op":"refs","va":"0x6793d8"}
```

- `explain` 回：这条指令、前后 5 条上下文、谁 call/jmp 它、碰哪个 `(base, disp)`、**以前有没有落过盘**（`archived`）。
- `near` 回：从这个地址起的连续指令（含原始字节）。
- `refs` 回：谁 `call/jmp` 到它，带前 6 条上下文。

**一个值往往有三条链路**（状态位 / 取模门 / 计数器）。只凭一条就下结论 = 赌。
必须用"同一基址 + 同一偏移"把几条链钉在一起（见 §六 的咬合速度案）。

### 第 6 步：落一处

```json
{"op":"land","site":"0x2793de","to":89,"width":1}
```

护栏（代码里写死的）：

| 情况 | 回执 |
|---|---|
| 站点不是本次 `ask/step` 出过的 | `site 0x… 不是这次 ask/step 出来的站点，先问出来再落` |
| 那里已经是目标值 | `那里已经是 89 了，没动` |
| 装不进宽度 | `300 装不进 1 字节` |
| 游戏开着锁文件 | `exe 被占用（游戏开着），文件没动` |
| 成功 | `ok:true` + `readback`（**重新打开文件读的**）+ `backup` + `archive` + `rollback` |

**只有 `readback == to` 才算成。** 注意：`seen` 为空时（从没 `ask` 过）站点校验不生效，
所以"冷启动直接 `land`"在代码层面拦不住 —— 自己别这么干。

### 第 7 步：进游戏验（肉眼 / 日志）

- 改了文件 ≠ 改了进程。**重启游戏**再看。
- 只看你要验的那一处：血量变了没、花费变了没、冷却短了没。
- 用户说没变 → 直接进 §八 的诊断顺序，不许让他"再打一局看看"。

### 第 8 步：记账与回滚

```json
{"op":"map","out":"地图/x"}     // 导出 json + md
{"op":"map","q":"阳光"}          // 按名字检索已落盘站点
```

`land` 已经把这次改动写进 `var/档案/<时间>_<name>.json`，备份在
`var/备份/<exe>.<md5前12>.bak`。

回滚 = 把备份拷回去。**在 git-bash / cygwin 里用 `cp -f`，不要用回执里那个 `copy`**
（`cmd //c copy` 在 cygwin 下实测静默不生效）：

```bash
cp -f "var/备份/x.exe.ec46d6b244c2.bak" "D:/games/x.exe"
```

---

## 三、判据表（`ask.kind`）

`help` 当前回的 10 条判据。`auto` 覆盖前 5 条，后 5 条必须显式写。

| kind | 放行条件 | 典型目标 | `from/to` 给什么 |
|---|---|---|---|
| `record` | 值在**名字锚定结构表**的某一列：同列 ≥3 份、有公因数、非占位、孤证让位 | 花费表、冷却表、任何带名字的表 | 表里的原值 → 新值，`width` 抄 `site_width` |
| `imm` | `mov [对象+偏移], 立即数`：基址非栈、`disp ≤ 0x1000`、独立回读等于 `from` | 单个常量：咀嚼 4000、冷却 1500、射速 200 | 立即数原值 → 新值 |
| `arm` | 值是**同一个 `cmp reg,k` 开关的另一档** | 分档常量（阳光 25→50）、按类型分支的初值 | 某一档的原值 → 新值 |
| `typed` | 值是 **f64 的某几个字节**，改完两边都还是"像样的 f64" | 400.0 → 100.0（改第 6 字节） | **字节值**：121 → 89，`width:1` |
| `f32` | 值是 **4 字节 float** 的某字节，且该常量被 `.text` 引用过 | 速度 0.23 → 0.46 | **字节值**，`width:1` |
| `addimm` | `add/sub [对象+偏移], 立即数`：目的非栈、`disp ≤ 0x1000`、独立回读；8 位立即数按**有符号**解释 | 僵尸每口咬 4 点血（`add [esi+0x40],-4`） | 每次扣减量 → 新量（`from:4` 同时吃 `+4/-4`） |
| `idtable` | **匿名类型表**：值在 `.data/.rdata`，同记录后面跟 `1,2,3…` 递增 id 列，同表 ≥6 条，步长 8~48 | `damage[type]` / `hp[type]` / `cost[type]` | 表里**任意一格**的值 → 新值；整表每格都会回成站点 |
| `typedref` | **被代码引用的 f64 倍率**：8 字节对齐、3 位以内小数、`|v| ≤ 1000` | 减速 0.4 → 0.1、0.5/1.5/0.25 类倍率 | **字节值**：217 → 185，`width:1` |
| `incdec` | `inc/dec [对象+偏移]`：复核 ModRM 的 reg 位，目的非栈帧 | 每帧 −1 的计数器、状态位 | 每次增减量 → 新量（`inc` 给 `1`） |
| `dataval` | **裸变量**：值在 `.data/.rdata`（4/8 字节对齐），且该地址被 `.text` 以绝对地址引用过 | C 风格全局变量 `int g_hp = 100;` | 原值 → 新值，`width:4/8` |

器官（只填证据，不排序）：`typed` `f32` `field` `addfield` `idtable` `f64ref`
`incdec` `dataval` `record` `store` `reg` `lea` `data`。

排序只有 GEDA 做（加权轮盘 `CLUE + dyn_weight + boost`），`step` 每发回灌。

---

## 四、op 全表（22 个，`help` 原样返回）

### 4.1 主流程（12 个）

| op | 必填 | 可选 | 作用 |
|---|---|---|---|
| `help` | — | — | 列 op / 判据 / 器官 / 窗口。**开工第一条** |
| `start` | `exe`, `from` | `to`, `width`, `name` | 建图（首次 ~20-30 s，之后有 pkl 秒开）+ 摸底 + 回档案 |
| `ask` | — | `kind`, `top`, `budget_s`, `window`, `from`, `to`, `width` | 一发查询，回排好序的站点 |
| `step` | — | `n`（≤20） | GEDA 按轮盘自己发 n 发并记账 |
| `techs` | — | — | 看学到的技术权重与命中（不需要 start） |
| `state` | — | — | 轮次 / 耗时 / 基因 / 经验池 / 策略 |
| `land` | `site`, `to` | `width` | 备份 → 写 → 独立回读 → 档案 |
| `map` | — | `out` 或 `q` | 导出地图册 / 按名字检索已落盘站点 |
| `near` | `va` | `n`, `exe` | 只读：某地址起连续指令 |
| `refs` | `va` | `exe` | 只读：谁 call/jmp 到它 |
| `explain` | `site` | `exe` | 只读：站点完整体检（指令/字段/引用/历史） |
| `stop` | — | — | 收工（serve 退出） |

### 4.2 活内存（10 个，只读，不改游戏内存一个字节）

先 `live_attach`，后面全部依赖它。**用途是定位对象与验证数值，不是改值。**

| op | 必填 | 可选 | 作用 |
|---|---|---|---|
| `live_attach` | `exe`（进程名） | — | 拿只读句柄，回 `pid / module / base / size` |
| `live_scan` | `value` | `width`(4), `max`(40), `heap`(true) | 哪些地址现在等于这个值 |
| `live_snap` | — | — | 内存快照，回 `snap` id（只留最近 3 张） |
| `live_diff` | — | `snap`, `max`(60), `align`(4) | 快照之后哪些 4 字节变了 → 找计数器 |
| `live_read` | `addr` | `n`(64) | 十六进制 + i32 视图 |
| `live_chain` | `addr`, `offsets` | — | 指针链：**根先解引用，中间每段读指针再偏移，最后一段是终点偏移不再解引用** |
| `live_rect` | `x`, `y` | `span`(24), `max`(30) | 哪个控件矩形包含这个点（找按钮） |
| `live_rects_page` | — | `min_area`(600), `max_area`(60000), `max`(60) | 列这一页所有像按钮的矩形 |
| `live_widgets` | `addr` | `n`(8), `stride`(0x60) | 顺着控件链列同类按钮 |
| `live_watch` | `keys` | — | 一次读一组命名值：`{"sun":"0x16f97010+0x5560"}` |

活内存的典型用法（找按钮，不用截图量像素）：

```json
{"op":"live_attach","exe":"PlantsVsZombies.exe"}
{"op":"live_snap"}                                  → s1
{"op":"live_diff","snap":"s1"}                      → 鼠标移动/点击后哪些数变了
{"op":"live_rect","x":555,"y":140}                  → 这个点在哪个控件里
{"op":"live_widgets","addr":"0x1712b6d8","n":8}     → 同一排按钮坐标
```

---

## 五、四类目标怎么开口（配方）

### 5.1 整数常量（血量 / 花费 / 上限）

```json
{"op":"start","exe":"...","from":270,"to":540,"width":4,"name":"hp"}
{"op":"ask","kind":"auto","top":10}
```

命中会标 `record`（表列）或 `arm`（分档）。同值多处时看 `evidence.table_names / votes`。
**单常量查不到时，补一发 `imm`。**

### 5.2 整张表（花费表 / 伤害表）

- 带名字 → `record`，看 `stride`（步长）、`delta`（列偏移）、`votes`（同列几行）。
- 没名字、后面跟 `1,2,3…` 递增类型号 → `idtable`，`from` 给表里任意一格，
  它把整张表每格都回成站点，**一格一格 land，一次只验一处**。

### 5.3 浮点

| 真身 | 判据 | `from → to` |
|---|---|---|
| `400.0 → 100.0`（整数 f64） | `typed` | 字节值：`121 → 89`，`width:1` |
| `0.4 → 0.1`（小数倍率） | `typedref` | 字节值：`217 → 185`，`width:1` |
| `0.23 → 0.46`（4 字节 float） | `f32` | 字节值，`width:1` |

`ask` 回执的 `evidence.f64` / `evidence.f32` 就是它在告诉你真身，别自己换算。

### 5.4 每次事件扣减的常量

```json
{"op":"start","exe":"...","from":4,"to":8,"width":1,"name":"bite"}
{"op":"ask","kind":"addimm","top":30}
```

`add [esi+0x40], -4` 这种写法 `imm` 门 0 命中，必须用 `addimm`。
`dec [esi+0x64]`（每帧 −1）用 `incdec`。

### 5.5 完全不认识的游戏

先跑 §二第 1 步的 `tools/survey.py`，再 `start` 看 `profile` / `presets`。
`gaps` 里有的形态（跳表、虚调用、Unity、ARM64），别硬碰 —— 明说做不了。

---

## 六、失败诊断（用户说"没变"就按这个顺序）

这是 2026-10-18 咬合速度案总结出来的，**顺序不许换**：

1. **先确认这段代码在目标场景里执行过**（命中面）。
   没执行 = 改错地方，不是改法不对。用 `explain` / `near` / `refs` 看。
2. **改"模 N"无效 → 立刻去看"计数器谁在写"。**
   调用方每 N 帧才进来一次时，模 N 恒成立，模数改成几都不影响。
3. **`cmp [obj+disp], 0` 这类字段先查有没有 `dec/inc`**（`incdec`）。
   没有增减点 = 它是状态位，不是计时器。
4. **一个值可能同时有三条链路**（状态位 / 取模门 / 计数器）。
   必须用"同基址 + 同偏移"交叉把三条钉死，凭一条下结论就是赌。

同时守上下文纪律：

- 一次手读最多看一个函数的前 40 条指令。
- 同一目标连续手查 3 轮没结论 → 停。换 `kind`、补器官、或告诉用户"缺哪个能力"。
- 禁止全量反汇编扫描，要扫用 `near/refs/explain`。
- 上下文过半就收尾、写交接、开新窗口。

---

## 七、排错表（回执原文 → 意思 → 怎么办）

| 回执 | 意思 | 怎么办 |
|---|---|---|
| `还没 start` | 引擎没载入 exe | 先 `start` |
| `exe 不存在：…` | 路径不对 | 用绝对路径；Windows 路径用 `/` 或 `\\` |
| `start 要给 from（要找的原值）` | 少 `from`，或 `from=0` | `from=0` 目前搜不了，换一个非零的锚点值 |
| `没给 from` | `ask` 时也没有 | 补 `from` |
| `没有判据通过` + `reasons` | 五条主判据都不认 | 看 `reasons` 差多少；按 §三 换显式 `kind` |
| `budget` | 超过 `budget_s`（默认 120） | **缩窄**目标或减 `top`，别加大预算 |
| `不认识的 kind：…` | kind 拼错或不在表里 | `{"op":"help"}` 看当前列表 |
| `… 判据没有站点` | 这条判据一无所获 | 换判据，别在原地重试 |
| `site 0x… 不是这次 ask/step 出来的站点` | 站点不是引擎给的 | 先 `ask`，落它给的 |
| `那里已经是 X 了，没动` | 重复落盘保护 | 正常，不用管 |
| `… 装不进 N 字节` | `to` 超宽 | 显式给对 `width`（常见：忘了写，被猜成 1） |
| `exe 被占用（游戏开着），文件没动` | 文件被锁 | 关游戏 |
| `进程不在：xxx` | `live_attach` 的进程名不对 | 用任务管理器里的**进程名**（带 `.exe`） |
| `先 live_attach` | 没挂进程 | 先 `live_attach` |
| `没有这个快照：s9` | 快照被淘汰（只留 3 张） | 重新 `live_snap` |
| `OpenProcess 失败：5` | 权限不足 | 用同权限运行；管理员游戏要管理员起引擎 |
| `JSON 解不动：…` | 一行不是合法 JSON | 一行一个对象，不跨行、不塞数组 |
| 中文崩 `gbk codec` | 没设编码 | `export PYTHONIOENCODING=utf-8` |
| 两次跑结果不同 | 旧 pkl 派生缓存 | 已修（派生缓存不进 pkl、键带版本）；仍疑虑就换 `var/map_*.pkl` 再跑 |
| `explain` 回的地址不对（x64） | `explain` 里 VA/FO 换算写死 `0x400000` | 64 位游戏只用 `near/refs` 传 VA，`explain` 只对 32 位准 |

---

## 八、落盘产物与磁盘

```
land → var/备份/<exe>.<md5前12>.bak        原文件整份备份
     → var/档案/<时间>_<name>.json         本次改了什么（含改前/改后 md5）
     → archive.remember(...)               目标履历（下次 start 的 recall）
```

- **每次改文件，md5 就变，建图缓存键也跟着变** → 同一游戏改三次会多出三张 80 MB 级 pkl。
  当前 `var/` 已 1.5 GB，就是 PvZ 多次落盘留下的。清理前先问用户，别自己删。
- 回滚用 `cp -f`（见 §二第 8 步）。
- 档案/备份是唯一能兜住"我判断错了"的东西，**不要删**。

---

## 九、边界（做不到的照实说，不许装作能打）

| 做不了 | 原因 | 现状 |
|---|---|---|
| gcc/clang/MSVC2015+ 的 `switch` 改档位 | 编成**跳表**，`arm` 只认 `cmp` 链 | `gate_jt` 未实现（通用性 4/6 的两个 ✗ 就在这） |
| 分清"同一 `disp` 在不同对象上" | 需要 `(对象, disp)` 身份 | `prov` 未做；虚调用形态属此列 |
| i16 / i8 常量 | 只做了 f64 / f32 | 未接 |
| Unity IL2CPP / Mono / ARM64 / ELF | 只认 PE + x86/x64 | 未接（预设里有条目，代码没有） |
| 读活内存改值 | `live_*` 是只读器官 | 要改值仍走 `ask → land` |
| 不重启游戏就生效 | 只动磁盘文件 | 必须重启 |
| 保证"改了有效果" | 有的字段没人读 | 看 `evidence`，或先小改一处验证 |
| Boss / 特殊模式自动识别 | 没有语义 | 给类型值，或用上限卡掉 |
| `from = 0` | 代码把 0 当"没给" | 换非零锚点 |

---

## 十、扩展（四步，都不改主流程）

### 10.1 加器官（新的"证据来源"）

丢一个文件，注册即生效：

```python
import registry as R

@R.organ("myorg", ["mygate"], "一句话说清它找什么")
def organ_myorg(m, value, goal=None):
    return [{"va": ..., "fo": ..., "fo_imm": ..., "imm": value,
             "mn": "...", "text": "..."}]
```

自检：`python tools/guard.py`（守卫 2 列出来，守卫 9 冒烟跑）。

### 10.2 加判据（新的"放行规则"）

```python
@R.gate("mygate", rank=1, prune="acc")
def gate_mygate(m, c, goal, window=0):
    return 10.0, {"gate": "mygate", "为什么": "..."}   # 不过就 return None
```

`ask{"kind":"mygate"}` 立刻可用（`niliu.py` 认注册表）。
要不要进 `auto`：改 `rules/规则.json` 的 `gates_order`，并用考试量一遍再加。

### 10.3 加形态预设

只改 `rules/预设.json`：`detect`（探针 + 阈值）、`response`、`status`。
`status` 只能 `ok/partial/todo`，写 `todo` 必须写 `缺口`。
自检：`python tools/guard.py`（守卫 12）。

### 10.4 加守卫

`tools/guard.py` 里加 `g13_xxx()` 并挂进 `main()`。
**新守卫必须能在被破坏时变红**（守卫 10 元测试会抽查）。

---

## 十一、文件地图

```
niliu.py         唯一入口：change（傻瓜）/ serve（常驻）/ task（批处理）/ land
core/hunt.py     主流程：recon → enum → rank → refine；GEDA 排序
core/geda.py     GEDA：加权轮盘、技术权重、经验池、热基因
core/registry.py 自注册表（organ / gate / policy）
core/map.py      建图：PE 解析（32/64）、反汇编、常量与字段
core/addr.py     操作数语法（[reg ± disp]、rip、变址、栈帧）
core/klass.py    走哪条判据
core/typed.py    f64 逐字节
core/typed32.py  f32 逐字节
core/field_imm.py mov [obj+disp], imm（判据 imm）
core/add_imm.py  add/sub [obj+disp], imm（判据 addimm）
core/id_table.py 匿名类型表（判据 idtable）
core/f64_ref.py  被引用的 f64 倍率（判据 typedref）
core/inc_dec.py  inc/dec 计数器（判据 incdec）
core/data_val.py 裸全局变量（判据 dataval）
core/record_table.py 名字锚定结构表（判据 record）
core/inspect_ops.py near / refs / explain（只读，把"读汇编"收进引擎）
core/mapbook.py  地图册（已落盘站点导出/检索）
core/live_ops.py 活内存只读器官（live_*）
core/archive.py  档案：结构记忆、目标履历
core/profile.py  摸底 → 选预设 → 能打/缺口
core/rules.py    规则读取（rules/规则.json 是参数总闸）
core/exam.py     考试（18 张卷）
core/replay.py   复刻器（按清单写字节）
core/tick.py / tree.py  Tick+Rng+Agent / 判定树（默认只观察）
rules/规则.json    阈值、先验、窗口、gates_order —— 唯一事实源头
rules/预设.json    13 条汇编形态预设
tools/guard.py      12 条结构守卫（每条都能变红）
tools/survey.py      单独摸底（PE/Rich/PDB/导入/汇编形态）
tools/同步skill.py docs/SKILL.md → 技能目录（回读 md5）
docs/USAGE.zh-CN.md    工具目录：现役 / PvZ 专项 / 一次性脚本
tests/generality.py    合成靶场（行为验证）
（内部研究脚本，未随发布版提供）             e01~e19 实验脚本（每个结论都能复现）
bench/            靶场源码与对打脚本
facts/            考试真值
examples/             历史实验 job（不是示例，示例在 examples/）
examples/         标准 job 示例（改个路径就能跑）
docs/             使用手册 / SKILL / 版本说明 / 交接 / 研究 / 首版说明书
var/             备份 + 档案 + 建图 pkl
```

---

## 十二、坑表（都实际踩过）

| 日期 | 症状 | 真因 | 修法 |
|---|---|---|---|
| 10-17 | `invalid choice` | 照旧技能写法带 `native` 子命令 | v3 只有 `serve` / `task` |
| 10-17 | 改了没变 | 写失败被当正常结果 | `land` 内建独立回读 |
| 10-17 | 血量 4 倍 | 同一 job 连按两次 `land` | 用备份还原后重放一次 |
| 10-17 | `PermissionError` | 游戏锁 exe | 先关游戏 |
| 10-17 | 中文崩 GBK | 没设编码 | `PYTHONIOENCODING=utf-8` |
| 10-17 | 同名同大小 exe 共用图 | 缓存键只看名+大小 | 已改内容 md5 |
| 10-17 | `cmd //c copy` 回滚没生效 | Windows/cygwin 路径转义静默失败 | 用 `cp -f` |
| 10-17 | 靶场找不到 400.0 | `const double` 被 `-O1` 折叠 | 靶子加 `volatile` |
| 10-17 | gcc switch 找不到 | 跳表，`arm` 只认 cmp 链 | 缺口，别硬碰 |
| 10-18 | 手查汇编几十轮，猜的站点全错 | 上下文灌满 → 反复换假设 | 3 轮没结论就停 |
| 10-18 | 单常量 `auto` 全查不到 | `auto` 不含 `imm` 等五条 | 显式 `kind` |
| 10-18 | 把 `call 0x5317C0` 当文件偏移 | 那是 VA | 读之前减基址 |
| 10-23 | 不写 `width` 时只改了低 1 字节 | 引擎按 `from > 0xFFFF ? 4 : 1` 猜；`to > 255` 才报"装不进" | **永远显式写 `width`**（`change` 会抄引擎的 `site_width`） |
| 10-23 | 冷启动直接 `land` 没被拦 | `seen` 为空时站点校验不生效 | 必须先进 `ask` |
| 10-23 | 同一游戏每改一次多一张 80 MB pkl | 缓存键含 md5 | 知道就行，清理先问用户 |
| 10-23 | x64 上 `explain` 地址不对 | VA/FO 换算写死 `0x400000` | 64 位只用 `near/refs` 传 VA |
| 10-23 | 摸底说"多半不是 MSVC 编的" | 无 Rich 头只说明**可能被抹**，不是结论 | 看链接器号（PvZ 8.0 = VS2005），别只凭 Rich |

---

## 十三、PvZ 1.0.0.1051 EN 事实库（32 位原生，实测）

| 项 | 值 |
|---|---|
| 位数 / 链接器 | 32 位 x86 / 8.0（VS2005 时代） |
| 时间戳 | 2009-04-21 06:21（`1240266083`） |
| Rich 头 | 没有（被抹）；静态 CRT，10 个 Win32 DLL |
| 规模 | `.text` 0x251000；761389 条指令；常量 252829；字段 285491 |
| 形态 | `cmp` 链 20423、跳表 **0**、`jmp reg` 55（虚调用）、变址 5944、字段写 72732、浮点 17412、名字表 23 |
| 基址 / 代码段 | `0x400000` / `.text 0x401000..0x652000` |
| 僵尸初始化 | `0x522580`（按类型分支写血量） |
| 血量字段 | `+0xc8`（本体）、`+0xd0` / `+0xdc`（护甲） |
| 血量原值 | 270/450/500/850/1350/3000；护甲 100/300/370/1100/1400/2200 |
| Boss | 类型 `0x20`，血 6000（`0x523d20` 附近）→ 改全体时用上限卡掉 |
| 阳光计数 | `board+0x5560`，上限 9990 |
| 阳光产出 | `0x4309D0` 按类型 4/5/6 → 25/15/50 |
| 传送带周期 | f64：`0x679628` / `0x6795E0` / `0x6798A0` / `0x6793D8`（400.0→100.0） |
| GameMode | `+0x7f8`；保龄球 = 35 |
| 咬合扣血 | `0x12FCF0` 的 `add dword ptr [esi+0x40], -4`（每口 4 点，`addimm`） |

---

## 十四、一句话

> **你给 `from → to`，它给几处带证据的站点；你落一处，它备份 + 回读 + 给回滚。**
> 它拒绝时别绕过去 —— 看它说的是哪条判据、缺哪个形态。
