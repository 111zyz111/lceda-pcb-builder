---
name: lceda-pcb-builder
description: >
  用嘉立创EDA专业版（EasyEDA Pro / LCEDA Pro）或 KiCad 画一块能投板的 PCB。
  覆盖需求 intake、LCSC 选型、原理图绘制与检查、封装建库、PCB 布局布线铺铜、
  DRC、BOM/网表、Gerber 投板放行与上电 bring-up。
  当用户提到画板、画个板子、PCB、原理图、封装、排母、牛角座、飞线、铺铜、位号、丝印、
  LCEDA、嘉立创、立创EDA、EasyEDA、KiCad、打样、投板、DRC、BOM、网表、
  ST-Link、USB转TTL、舵机接口、电机驱动、摄像头 FIFO 等接口需求时使用。
  不适用于纯结构外壳设计、IC 版图设计或 FPGA 逻辑设计。
metadata:
  version: "1.0.0"
  primary_tool: "嘉立创EDA专业版 (EasyEDA Pro) via MCP bridge"
  fallback_tool: "KiCad (kicad-cli / 文件生成)"
  language: "zh-CN"
---

# 画板：从需求到能投板的 PCB

把「一句话需求」变成「能打样的板子」。中文回答，先结论后依据。

双路径，按用户环境选：

| 路径 | 适用条件 | 入口文档 |
|---|---|---|
| **A. 嘉立创EDA专业版（主）** | 本机装有专业版，且有 MCP 桥（`mcp-bridge-community` / `easyeda-agent` / `jlcmcp` 任一） | [references/mcp-playbook.md](references/mcp-playbook.md) |
| **B. KiCad 离线生成（兜底）** | 无专业版、断网、或需要 Git diff/CI 复现 | [references/kicad-fallback.md](references/kicad-fallback.md) |

两条路径共用同一套纪律与自检脚本，产物都是同一张 `net-table.csv`。

---

## 八条硬规则（每次画板都生效，不可跳过）

1. **不凭截图猜连接。** 所有连接以读到的真实工程数据、数据手册原文、实测尺寸为准。
2. **不凭记忆编造。** 引脚定义、LCSC 料号、封装尺寸、价格库存一律现查；查不到写「待核实」，不填空。
3. **写入必回读。** 每个写操作后调用对应 `*_read` 工具对账（图元 ID / 网络 / 几何逐项核对）；
   对账不通过即回滚并报告，不静默继续。
4. **确定性计算跑脚本，禁止心算。** 线宽、载流、压降、温升、阻抗、分压、RC 截止频率、
   电池续航一律 `python scripts/pcbcalc.py`。
5. **单一权威源。** 所有连接先落成 `net-table.csv`（列：位号,引脚,网络,MCU引脚名,备注），
   原理图与 PCB 都从它派生；改设计只改 CSV。
6. **四类信息分开标注。** 【事实】给来源位置；【推断】列依据与可验证条件；
   【建议】说明取舍；【阻塞项】先问再动。不得混淆。
7. **高风险显式声明边界。** 强电、锂电池、射频、车载、医疗场景必须要求人工复核，
   不得声称「已认证」「已合规」。
8. **批量改动前先备份。** 确认工程已保存或已有版本控制，再进行批量写入。

---

## 五道闸门

每道闸门有明确放行条件，未通过不得进入下一道。

### Gate 1 需求 intake
读 [references/intake.md](references/intake.md)。

产出：需求清单 + **阻塞项** + 保守假设表 + 方块图 + 电源树草案。
放行条件：阻塞项已答复或用户明确授权按假设继续。

### Gate 2 选型与建库
读 [references/lcsc-sourcing.md](references/lcsc-sourcing.md)。

产出：BOM 草案（每个器件标注 型号/封装/LCSC C号/来源/验证状态）。
放行条件：每个器件都有「已核实」或「待核实」标注；无凭空编造的料号。

### Gate 3 原理图
读 [references/schematic-rules.md](references/schematic-rules.md)、
[references/mcu-pinmap.md](references/mcu-pinmap.md)。

产出：`net-table.csv` + 原理图 + ERC/DRC 报告。
放行条件：`scripts/netlist_check.py` 对账通过 + 官方 sch DRC 无 error。

### Gate 4 PCB 布局布线
读 [references/pcb-rules.md](references/pcb-rules.md)。

产出：板框、叠层、分区布局、布线、铺铜、丝印 + DRC 报告。
放行条件：官方 PCB DRC 无 error；`scripts/bom_check.py` 一致性通过。

### Gate 5 投板放行与 bring-up
读 [references/verification.md](references/verification.md)。

产出：`scripts/release_audit.py` 报告 + Gerber/BOM/CPL 包 + 上电步骤。
放行条件：go/no-go 结论 + 必须人工复核项单独列出。

---

## 路由表

| 用户请求 | 先读 | 视情况再读 |
|---|---|---|
| 画一块新板 | intake.md | lcsc-sourcing.md, mcu-pinmap.md |
| 改 / 修已有板 | mcp-playbook.md | verification.md, pitfalls.md |
| 根据数据手册建库 | mcp-playbook.md | lcsc-sourcing.md |
| 器件标准化（换标准料） | lcsc-sourcing.md | verification.md |
| 投板前检查 | verification.md | pcb-rules.md |
| 算线宽 / 分压 / 温升 / 续航 | `scripts/pcbcalc.py --help` | pcb-rules.md |
| 无专业版，用 KiCad | kicad-fallback.md | pitfalls.md |
| 上电调试 | templates/bringup-log.md | verification.md |

---

## 输出契约

### 新板
1. 阻塞项与保守假设表；2. 方块图 + 电源树；3. 引脚分配表；
4. `net-table.csv`；5. BOM（含验证状态）；6. 布局布线/叠层/热/测试约束；
7. 风险登记与下一动作。

### 改板
1. 先报「读到的真实状态」；2. 变更清单；3. 回读对账结果；4. 仍需人工决策的问题。

### 投板放行
1. 文件齐全性；2. DRC/ERC 状态；3. BOM/CPL 一致性；4. 未决供应商问题；
5. go / no-go 结论与必须人工复核项。

### 每阶段收尾（固定格式）
```
【本阶段】做了什么 / 实际结果 / 验证证据 / 剩余问题 / 建议 / 下一阶段提示词
```

---

## 严重度分级（评审类输出统一使用）

| 级别 | 含义 |
|---|---|
| **Critical** | 阻断投板、可能损坏硬件、违反安全、使必需功能不可能实现 |
| **Major** | 很可能功能失败、良率低、可靠性风险、合规问题 |
| **Minor** | 成本、可制造性、可维护性、鲁棒性改进 |
| **Question** | 缺失信息，可能改变结论 |

每条发现必须给证据：文件/行号、网络名、数据手册章节、测量值或显式假设。
无证据就说无证据，不用推测填充。

---

## 规则优先级（冲突时按此顺序）

1. 用户需求与适用安全/法规标准
2. 器件数据手册、参考设计、勘误表
3. 当前厂商工艺能力与所选叠层
4. 项目专属设计规则
5. 本 Skill 的通用规则

---

## 已知局限

- 本 Skill 不调用 KiCad 官方 DRC（未检测到 `kicad-cli`）；KiCad 路径下以自研脚本校验 + 用户人工跑 DRC。
- 嘉立创 EDA 菜单路径、快捷键、导出文件名随版本变化，执行前需确认实际界面。
- 自动布局/自动布线在两侧均为 BETA，结果必须人工复核。
