# lceda-pcb-builder

[![selftest](https://github.com/111zyz111/lceda-pcb-builder/actions/workflows/selftest.yml/badge.svg)](https://github.com/111zyz111/lceda-pcb-builder/actions/workflows/selftest.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

用 **嘉立创EDA专业版（EasyEDA Pro / LCEDA Pro）** 或 **KiCad** 画一块能投板的 PCB。

主入口是 [SKILL.md](SKILL.md)。本文件是给人看的说明。

## 它解决什么问题

AI 画板最常见的三类失败：

1. **凭记忆/截图编数据** —— 引脚定义、LCSC 料号、封装尺寸是假的
2. **写入不回读** —— 静默失败，后面对账全线崩
3. **心算关键数值** —— 线宽、分压、温升算错

本 Skill 用三条纪律压住它们：**单一权威源**、**写入必回读**、**确定性计算跑脚本**。

## 目录

```
lceda-pcb-builder/
├─ SKILL.md                  # 主入口：触发器、八条硬规则、五道闸门、路由表、输出契约
├─ README.md                 # 本文件
├─ references/
│   ├─ intake.md             # Gate 1：阻塞项 vs 可假设项
│   ├─ lcsc-sourcing.md      # Gate 2：LCSC 选型、建库
│   ├─ schematic-rules.md    # Gate 3：命名、位号、常见接口连接
│   ├─ pcb-rules.md          # Gate 4：布局布线铺铜丝印 DRC
│   ├─ mcu-pinmap.md         # 引脚分配约束与冲突检查
│   ├─ verification.md       # Gate 5：自检、放行、bring-up
│   ├─ mcp-playbook.md       # 路径 A：58 个 MCP 工具、参数陷阱、回读范式
│   ├─ kicad-fallback.md     # 路径 B：KiCad 离线生成
│   └─ pitfalls.md           # 已知坑清单
├─ scripts/
│   ├─ pcbcalc.py            # 确定性计算（零依赖）
│   ├─ netlist_check.py      # net-table.csv ↔ 网表 双向对账
│   ├─ bom_check.py          # BOM/CPL 一致性 + 位号冲突
│   └─ release_audit.py      # 制造文件完整性审计
├─ tests/
│   └─ run_selftest.py       # 21 项回归自测
└─ templates/
    ├─ design-brief.md
    ├─ net-table.csv
    └─ bringup-log.md
```

## 快速开始

```bash
# 1. 回归自测（21 项，零依赖）
python tests/run_selftest.py

# 2. 新建项目：先填需求
cp templates/design-brief.md <项目>/design-brief.md

# 3. 落权威源：所有连接只改这个文件
cp templates/net-table.csv <项目>/net-table.csv

# 4. 画完原理图后对账（必须 0 差异）
python scripts/netlist_check.py <项目>/net-table.csv <导出的网表.csv>

# 5. 投板前放行
python scripts/bom_check.py bom.csv cpl.csv
python scripts/release_audit.py <gerber目录> --bom bom.csv --cpl cpl.csv --layers 4
```

## 计算器

```bash
python scripts/pcbcalc.py --help
python scripts/pcbcalc.py trace --current 1.5 --copper 1oz
python scripts/pcbcalc.py divider --vin 12 --r1 10k --r2 2k
python scripts/pcbcalc.py thermal-ldo --vin 12 --vout 5 --iout 0.3 --rth 60
python scripts/pcbcalc.py battery --mah 2000 --ma 150
python scripts/pcbcalc.py rc --r 10k --c 100n
python scripts/pcbcalc.py buck-inductor --vin 12 --vout 5 --iout 1
python scripts/pcbcalc.py thermal-shunt --i 2 --r 0.05
python scripts/pcbcalc.py resistor-power --v 5 --r 1k
python scripts/pcbcalc.py via --current 2 --drill 0.3 --plate 0.6
```

所有结果是**工程估算**，不是保证值。关键设计需厂方叠层或场仿真确认。

## 路径选择

| 路径 | 条件 | 文档 |
|---|---|---|
| A. 嘉立创EDA专业版 | 装有专业版 + MCP 桥 | [references/mcp-playbook.md](references/mcp-playbook.md) |
| B. KiCad 离线 | 无专业版 / 断网 / 需 Git diff | [references/kicad-fallback.md](references/kicad-fallback.md) |

两条路径共用同一套纪律、同一份 `net-table.csv`。

## 已知局限

- 未调用 KiCad 官方 DRC（本机可能无 `kicad-cli`）；KiCad 路径下以自研脚本校验，
  交付说明中必须告知用户"官方 DRC 未跑，请人工跑一次"。
- 嘉立创 EDA 菜单/快捷键/导出文件名随版本变化，执行前需确认实际界面。
- 自动布局/自动布线两侧均为 BETA，结果必须人工复核。

## 参考来源

方法论吸收自以下开源项目（未复制其代码）：

| 项目 | ★ | 许可 | 取什么 |
|---|---|---|---|
| `zhoushoujianwork/easyeda-agent` | 685 | MIT | 写入前检查→写入→回读对账三段式 |
| `easyeda/easyeda-api-skill` | 921 | 无 | 官方 `eda.*` API 与文档格式（仅参考，不抄代码） |
| `easyeda/easyeda-format-skill` | 11 | MIT | 专业版格式规则与强制校验思想 |
| `aklofas/kicad-happy` | 1416 | MIT | 48 个零依赖解析/校验脚本的思路 |
| `SPREsxm/claude-pcb-designer` | 8 | MIT | 确定性计算器、严重度分级、LCEDA 工作流 |

KiCad 兜底路线可选（均 MIT）：atopile (3993★)、KiKit (2043★)、
InteractiveHtmlBom (4603★)、kicad-jlcpcb-tools (2110★)、easyeda2kicad.py (1701★)。

**明确不采纳**：`INTI-CMNB/KiBot`（AGPL-3.0 传染）、
`Zane456/PCB-Agent-Teams`（PolyForm NC 禁商用 + 仅 macOS）、
已停更的 `KiCad/kicad-footprints` 与 `Digi-Key/digikey-kicad-library`。
