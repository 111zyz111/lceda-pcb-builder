# KiCad 离线路径（路径 B）

适用：没有嘉立创专业版、断网、或需要 Git diff / CI 复现的场景。
嘉立创EDA专业版**可以直接导入 KiCad 文件**，所以这条路产的资产仍能进嘉立创。

## 1. 格式选择

| 载体 | 用途 | 注意 |
|---|---|---|
| `.kicad_sch` | 原理图 | S 表达式，人类可读，Git 友好 |
| `.kicad_pcb` | PCB | 同一文件内可内嵌封装 |
| `.kicad_sym` | 符号库 | 独立文件 |
| `.pretty/*.kicad_mod` | 封装库 | 用户要求单文件交付时避免单独发 |
| `.kicad_mod` 内嵌进 `.kicad_pcb` | **单文件交付** | 用户说"不要搞 mod"时用这个 |

## 2. 生成要点（程序化生成时）

- **权威源**：先有 `net-table.csv`，再生成图
- **Y 轴**：符号库 Y 向上，原理图/PCB Y 向下，转换必须取负（见 pitfalls.md）
- **引脚坐标**：从符号定义算，不要猜
- **坐标单位**：KiCad 全部 mm
- **自检**：括号平衡、符号/实例/库引用齐全、走线端点在图元上、
  每个引脚都有网络标签或走线、网表与 CSV 双向对账
- **不要手写嘉立创标准版 JSON**：其格式闭源且版本敏感。专业版格式可参考官方
  `easyeda/easyeda-format-skill`（MIT）

## 3. 工具链

```bash
# DRC / 导出（若本机有 kicad-cli）
kicad-cli sch erc  <project.kicad_sch>
kicad-cli pcb drc  <board.kicad_pcb>
kicad-cli pcb export gerbers <board.kicad_pcb> -o out/gerber
kicad-cli pcb export drill   <board.kicad_pcb> -o out/gerber
```

本机可能未装 KiCad。**未检测到 `kicad-cli` 时，本 Skill 的自研脚本是唯一校验层**，
必须在交付说明中明确告知用户"官方 DRC 未跑，请在 KiCad/嘉立创中人工跑一次"。

## 4. 生成后的自检脚本

```bash
python scripts/netlist_check.py net-table.csv <导出的网表.csv>
python scripts/release_audit.py <gerber目录> --json
```

## 5. 可选增强（按需，均为 MIT）

| 项目 | ★ | 用途 |
|---|---|---|
| `atopile/atopile` | 3993 | Python 写电路，模块化复用，编译出 KiCad 网表 |
| `devbisme/skidl` | 1693 | Python → 网表 → pcbnew，成熟稳定 |
| `yaqwsx/KiKit` | 2043 | 拼板与制造输出自动化 |
| `openscopeproject/InteractiveHtmlBom` | 4603 | 交互式装配 BOM（同时支持 EasyEDA） |
| `Bouni/kicad-jlcpcb-tools` | 2110 | 给器件打 LCSC 料号、导出 JLCPCB BOM+CPL |
| `uPesy/easyeda2kicad.py` | 1701 | LCSC 元件 → KiCad 符号/封装/3D |
| `aklofas/kicad-happy` | 1416 | 48 个零依赖 Python 解析/校验脚本，自检层范本 |

**不采纳**：`INTI-CMNB/KiBot`（AGPL-3.0，传染性）。
**已停更不采纳**：`KiCad/kicad-footprints`（2021）、
`Digi-Key/digikey-kicad-library`（2024）、`curtacircuitos/pcb-tools`（2024）。

## 6. 从 KiCad 转回嘉立创

嘉立创EDA专业版支持导入 KiCad 文件。导入后必须：

1. 回读全部器件与网络，与 `net-table.csv` 对账
2. 检查封装是否齐全（部分封装需手动补）
3. 重跑 DRC
4. 不要假设导入即正确
