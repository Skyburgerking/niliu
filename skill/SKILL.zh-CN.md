---
name: niliu-injection-engine
description: 驱动 niliu 引擎改单机游戏二进制里的数值，不读汇编。你只吐 JSON（start/ask/step/land），引擎负责找带证据的站点，并做备份 + 独立回读 + 回滚。适用：血量、花费、冷却、伤害、速度、数量；不知道值从哪来；改了没反应；要回滚改坏的游戏；判断某个游戏能不能做。前提：已安装 niliu 引擎（github.com/Skyburgerking/niliu），并由支持工具调用的 LLM 驱动。关键词：逆流、niliu、改数值、金手指、修改器、PE、x86、x64、from、to、width、start、ask、step、land、判据、器官、record、imm、arm、typed、f32、addimm、idtable、typedref、incdec、dataval、GEDA、加权轮盘、证据、回读、备份、回滚、档案、跳表、虚调用、PvZ。
---

# 逆流 v3 · 执行卡

> 引擎：**github.com/Skyburgerking/niliu**（只有这一套）。
> 本页是**给 LLM 的执行卡**，不是手工改游戏的教程。
> 卡片与引擎冲突时，以引擎 `{"op":"help"}` 的实回为准。

---

## 开工前提

1. **用 LLM 代理来干这活。** 本卡假设模型能调用工具、能读 JSON 回执；「自己读汇编找地址」明确不在范围内。
2. **装好引擎**：Python 3.10+、`capstone>=5.0`、Windows、PE x86/x64 目标。
3. **只改自己的单机游戏**，用于个人使用与学习；不用于联机、竞技或商业作弊。改什么由你负责。
4. **先备份 exe。** `land` 会自动备份，自己也留一份。
5. **先关游戏**：运行中的进程会锁文件。

---

## 三条铁律

1. **「没成」就是没成。** 不许让用户「再打一局看看」，不许解释成「可能你没注意到」。
   唯一结论是**你没定位到消费点**。
2. **不许自己读汇编找站点。** 不写 capstone 循环、不手算偏移、不手拼补丁。
   读汇编只走引擎三个只读口：`near` / `refs` / `explain`。
3. **一次只改一处。** 落完立刻回读，只交能肉眼验收的那一处。

配套：**落盘只认本次 `ask`/`step` 回过的 `site`**；**同一目标绝不连按两次 `land`**（实测 540 → 1080）。

---

## 上下文纪律

手读汇编吃上下文，吃到一半模型会反复换假设、把某个偏移当真理。

1. 一次手读最多看**一个函数的前 40 条指令**，超过就停。
2. 同一目标连续 **3 轮**没结论 → 立刻停。换 `ask kind=<另一条判据>` / 补器官 / 直说「做不了，缺哪个能力」。
3. 禁止全量反汇编扫描。要扫用 `near/refs/explain`，或让 `ask` 扫。
4. 禁止用十六进制裸读去「确认」。要确认就 `land` + 独立回读，或进游戏实测。
5. 上下文过半就收尾：写交接、开新窗口。

---

## 入口

```bash
export PYTHONIOENCODING=utf-8      # Windows 不设，中文输出可能崩 GBK

# 一条命令（默认只看不写，--write 才落第 1 条）
python niliu.py change "D:/games/x.exe" 150 75
python niliu.py change "D:/games/x.exe" 150 75 --write

# 高级：自己挑站点 / 看完整回执
python niliu.py serve              # 先吐一行 hello，之后一行 JSON 进一行出
python niliu.py task examples/02_table_column.json
```

`change` 内部就是 `start → ask → land`，护栏一条不少；`--kind` / `--width` / `--top` 可覆盖默认。

---

## 标准流程（八步）

```
0 关游戏            → land 改磁盘 exe，开着会锁文件
1 摸底              → python tools/survey.py <exe>，或 start 后看 profile / presets
2 定目标            → start{exe,from,to,width,name}；width 永远显式写
3 选判据            → 先 ask{kind:"auto"}，不对路再显式换 kind
4 读回执            → site / va / site_width / score / evidence / n
5 交叉验证          → explain + near + refs，同一 (base,disp) 钉死
6 落一处            → land{site,to,width}，readback == to 才算成
7 进游戏验          → 重启游戏，只看这一处
8 记账/回滚         → map 导出；回滚 cp -f 备份回去
```

### 第 2 步的硬规矩

| 字段 | 规矩 |
|---|---|
| `from` | 磁盘 exe 里的原值，不是游戏里显示值。**`from = 0` 不支持**（按「没给」处理） |
| `to` | 新值，必须装得进 `width` |
| `width` | **永远显式写。** 不写时按 `from > 0xFFFF ? 4 : 1` 猜：`from=100` 猜成 1 字节，4 字节字段只改低字节；`to > 255` 直接报装不进 |
| `name` | 目标名，进档案，方便 `archive.recall` |

`site_width` 是该站点要改几字节；数据站点没有常量条目时会回退成 `goal.width` —— 落盘前和 `evidence` 对一遍。

---

## 协议（22 个 op）

### 主流程 12 个

| op | 必填 | 可选 | 作用 |
|---|---|---|---|
| `help` | — | — | 列 op / 判据 / 器官 / 窗口。**开工第一条** |
| `start` | `exe`,`from` | `to`,`width`,`name` | 建图（首次 ~20-30 s，之后缓存秒开）+ 摸底 + 档案 |
| `ask` | — | `kind`,`top`,`budget_s`,`window`,`from`,`to`,`width` | 一发查询，回排好序的站点 |
| `step` | — | `n`(≤20) | GEDA 按轮盘发 n 发并记账 |
| `techs` | — | — | 技术权重与命中（不需 start） |
| `state` | — | — | 轮次 / 耗时 / 基因 / 经验池 |
| `land` | `site`,`to` | `width` | 备份 → 写 → 独立回读 → 档案 |
| `map` | — | `out` 或 `q` | 导出地图册 / 按名字检索 |
| `near` | `va` | `n`,`exe` | 只读：某地址起连续指令 |
| `refs` | `va` | `exe` | 只读：谁 call/jmp 到它 |
| `explain` | `site` | `exe` | 只读：站点完整体检 |
| `stop` | — | — | 收工 |

### 活内存只读 10 个（不改内存一个字节）

先 `live_attach{exe:"进程名.exe"}`，其余都依赖它。

| op | 必填 | 可选 | 作用 |
|---|---|---|---|
| `live_attach` | `exe` | — | 只读句柄，回 pid/module/base/size |
| `live_scan` | `value` | `width`(4),`max`(40),`heap`(true) | 哪些地址现在等于这个值 |
| `live_snap` | — | — | 快照，回 snap id（只留最近 3 张） |
| `live_diff` | — | `snap`,`max`(60),`align`(4) | 快照后哪些 4 字节变了 |
| `live_read` | `addr` | `n`(64) | 十六进制 + i32 |
| `live_chain` | `addr`,`offsets` | — | 指针链：根先解引用，中间读指针再偏移，最后一段是终点偏移 |
| `live_rect` | `x`,`y` | `span`(24),`max`(30) | 哪个控件矩形包含这个点 |
| `live_rects_page` | — | `min_area`(600),`max_area`(60000),`max`(60) | 这一页所有像按钮的矩形 |
| `live_widgets` | `addr` | `n`(8),`stride`(0x60) | 顺控件链列同类按钮 |
| `live_watch` | `keys` | — | 一组命名值：`{"sun":"0x16f97010+0x5560"}` |

活内存用来定位对象、验证数值、找按钮坐标；**改值仍走 `ask → land`（磁盘）**。

---

## 判据表（`ask.kind`）

`auto` 只跑前 5 条：`record → imm → arm → typed → f32`。后 5 条必须显式写。

| kind | 放行条件 | 典型目标 | `from/to` |
|---|---|---|---|
| `record` | 名字锚定结构表某一列：同列 ≥3、公因数、非占位、孤证让位 | 花费表、冷却表 | 原值 → 新值 |
| `imm` | `mov [obj+disp], imm`：基址非栈、`disp≤0x1000` | 单个常量（4000/1500/200） | 立即数 |
| `arm` | 值是同一 `cmp reg,k` 开关的另一档 | 分档常量（25 → 50） | 某一档 |
| `typed` | 值是 f64 的某几个字节，改完两边都还像样 | 400.0 → 100.0 | **字节值** 121 → 89，`width:1` |
| `f32` | 4 字节 float 的某字节，常量被 `.text` 引用 | 0.23 → 0.46 | **字节值**，`width:1` |
| `addimm` | `add/sub [obj+disp], imm`：目的非栈、`disp≤0x1000`、8 位立即数按有符号 | 每次事件扣减量 | 每次扣减 |
| `idtable` | 匿名类型表：值在 `.data/.rdata`，后跟 `1,2,3…` id 列，≥6 条，步长 8~48 | `damage[type]` / `hp[type]` | 表里任意一格 |
| `typedref` | 被引用的 f64 倍率：8 字节对齐、3 位小数内、`|v|≤1000` | 0.4 → 0.1 | **字节值** 217 → 185 |
| `incdec` | `inc/dec [obj+disp]`，复核 ModRM reg 位，目的非栈 | 每帧 −1 计数器 | 每次增减 |
| `dataval` | 裸变量：`.data/.rdata` + 被 `.text` 绝对地址引用 | `int g_hp=100;` | 原值 → 新值，`width:4/8` |

器官（只填证据，不排序）：`typed` `f32` `field` `addfield` `idtable` `f64ref` `incdec` `dataval`
`record` `store` `reg` `lea` `data`。

排序只有 GEDA 做（`CLUE + dyn_weight + boost` 加权轮盘），`step` 每发回灌。

---

## 回执怎么读

```json
{"ok":true,"gate":"typed","window":48,"n":1,"site_width":1,
 "rows":[{"site":"0x2793de","va":"0x6793de","text":"f64 @0x2793d8 第6字节",
          "score":12.0,"evidence":{"gate":"typed","f64":[400.0,100.0],"byte":6,"ratio":0.25}}]}

{"ok":true,"site":"0x2793de","width":1,"from":121,"to":89,"readback":89,
 "backup":"var/backups/x.exe.ec46d6b244c2.bak","archive":"20261017_223534_demo",
 "rollback":"cp -f \"var/backups/...bak\" \"D:/games/x.exe\""}
```

- `site` = **文件偏移**（也接受 VA，引擎会减基址）。`va` 给 `near/refs/explain`。
- 同分多行时**不要按顺序挑**，看 `evidence` 分辨：表名/`votes`/`gcd` > 纯生产者 vs 累加器 > 分档集 > 引用证据 > 位置常识。
- `readback == to` 才算成功（回读是重新打开文件读的，不是缓存）。

---

## 落盘与回滚

```
land → var/backups/<exe>.<md5前12>.bak
     → 写 + fsync
     → 重开文件独立回读
     → var/archives/<时间>_<name>.json
```

回滚 = 把 `.bak` 拷回去。Windows 上别依赖回执里的 `copy`（cygwin 下实测静默不生效），用：

```bash
cp -f "var/backups/x.exe.ec46d6b244c2.bak" "D:/games/x.exe"
```

护栏：站点必须来自本次 `seen`（**冷启动 `seen` 为空，校验不生效 —— 必须先 `ask`**）；
已是目标值拒；装不进宽度拒；文件被占用拒；写完独立回读。

---

## 失败诊断（用户说「没变」就按这个顺序）

1. **先确认这段代码在目标场景里执行过**（命中面）。没执行 = 改错地方，不是改法不对。
2. **改「模 N」无效 → 立刻去看「计数器谁在写」。** 调用方每 N 帧才进来一次时，模 N 恒成立。
3. **`cmp [obj+disp],0` 先查有没有 `dec/inc`。** 没有增减点 = 状态位，不是计时器。
4. **一个值可能有三条链路**（状态位 / 取模门 / 计数器），用「同基址 + 同偏移」交叉钉死，凭一条下结论就是赌。

---

## 验收（改完引擎就跑）

```bash
python tools/guard.py              # 12 条结构守卫，必须全绿
python core/exam.py <pvz.exe> 30   # 18 张卷
python tests/generality.py         # 不依赖游戏的合成靶场
```

2026-10-23 实测：

```
守卫 12/12 绿（13 器官、13 预设、能打 4 / 缺口 5）
考试 14/18，平均 F1 0.778
通用性 4/6（表列 ✓✓ 浮点 ✓✓ 分档 ✗✗）
```

**这是「不许退化」的底线，不是毕业。** 毕业线：考试 18/18 **且** 通用性 6/6。

---

## 边界（做不到的照实说）

- **跳表 switch**（gcc/clang/MSVC2015+）：`gate_jt` 未实现，`arm` 只认 `cmp` 链。
- **虚调用 / 对象身份**：`prov` 未做，分不清同一 `disp` 在不同对象上。
- **i16 / i8 常量**：只做了 f64 / f32。
- **Unity IL2CPP / Mono / ARM64 / ELF**：只认 PE + x86/x64。
- **活内存改值**：`live_*` 只读；改值仍走磁盘。
- **不重启就生效**：做不到，只动磁盘文件。
- **保证改了有效果**：做不到，有的字段没人读。
- **Boss / 特殊模式**：不自动识别，给类型值或用上限卡掉。
- **`from = 0`**：不支持，代码把 0 当「没给」。
- **x64 的 `explain`**：VA/FO 换算写死 `0x400000`，64 位只用 `near/refs` 传 VA。

---

## 附：PvZ 1.0.0.1051 EN 事实库（32 位原生）

| 项 | 值 |
|---|---|
| 位数 / 链接器 | 32 位 x86 / 8.0（VS2005） |
| 时间戳 | 2009-04-21 06:21（`1240266083`） |
| Rich 头 | 无（被抹）；静态 CRT，10 个 Win32 DLL |
| 规模 | `.text` 0x251000；761389 指令；252829 常量；285491 字段 |
| 形态 | cmp 链 20423、跳表 **0**、`jmp reg` 55（虚调用）、变址 5944、字段写 72732、浮点 17412、名字表 23 |
| 基址 / 代码段 | `0x400000` / `.text 0x401000..0x652000` |
| 僵尸初始化 | `0x522580` |
| 血量字段 | `+0xc8`；护甲 `+0xd0`/`+0xdc` |
| 血量原值 | 270/450/500/850/1350/3000；护甲 100/300/370/1100/1400/2200 |
| Boss | 类型 `0x20`，血 6000 |
| 阳光 | 计数 `board+0x5560`（上限 9990）；产出 `0x4309D0`（4/5/6 → 25/15/50） |
| 传送带周期 | f64：`0x679628`/`0x6795E0`/`0x6798A0`/`0x6793D8` |
| GameMode | `+0x7f8`；保龄球 = 35 |
| 咬合扣血 | `0x12FCF0`：`add dword ptr [esi+0x40], -4`（`addimm`） |

> 只对这一个版本有效，换版本全部偏移都会变。

---

## 坑表（都实际踩过）

| 日期 | 症状 | 真因 | 修法 |
|---|---|---|---|
| 10-17 | `invalid choice` | 照 v1 写法带 `native` | v3 只有 `change`/`serve`/`task` |
| 10-17 | 改了没变 | 写失败被当正常结果 | `land` 内建独立回读 |
| 10-17 | 血量 4 倍 | 同一 job 连按两次 `land` | 用备份还原后重放一次 |
| 10-17 | `PermissionError` | 游戏锁 exe | 先关游戏 |
| 10-17 | 中文崩 GBK | 没设编码 | `PYTHONIOENCODING=utf-8` |
| 10-17 | 同名同大小 exe 共用图 | 缓存键只看名+大小 | 已改内容 md5 |
| 10-17 | `cmd //c copy` 回滚没生效 | cygwin 转义静默失败 | 用 `cp -f` |
| 10-17 | 靶场找不到 400.0 | `const double` 被折叠 | 靶子加 `volatile` |
| 10-17 | gcc switch 找不到 | 跳表 | 缺口，别硬碰 |
| 10-18 | 手查汇编几十轮猜的站点全错 | 上下文灌满 → 反复换假设 | 3 轮没结论就停 |
| 10-18 | 单常量 `auto` 查不到 | `auto` 不含 `imm` 等五条 | 显式 `kind` |
| 10-18 | `call 0x5317C0` 当文件偏移 | 那是 VA | 读前减基址 |
| 10-23 | 不写 `width` 只改了低 1 字节 | 按 `from > 0xFFFF ? 4 : 1` 猜；`to > 255` 才报装不进 | **永远显式写 `width`** |
| 10-23 | 冷启动直接 `land` 没被拦 | `seen` 为空时校验不生效 | 必须先 `ask` |
| 10-23 | 每改一次多一张 80 MB 缓存 | 缓存键含 md5 | 知道就行，定期清 `var/` |
| 10-23 | x64 上 `explain` 地址不对 | 换算写死 `0x400000` | 64 位只用 `near/refs` |
| 10-23 | 摸底说「多半不是 MSVC」 | 无 Rich 只说明可能被抹 | 看链接器号 |

---

## 一句话

> **你给 `from → to`，它给几处带证据的站点；你落一处，它备份 + 回读 + 给回滚。**
> 它拒绝时别绕过去 —— 看它说的是哪条判据、缺哪个形态。
