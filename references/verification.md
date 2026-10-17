# 自检与投板放行

## 0. 改动脚本后先跑回归

```bash
python tests/run_selftest.py     # 21 项，零依赖
```

任何计算器或审计行为改动，先在 `tests/run_selftest.py` 里加对应断言再改实现。

## 1. 三个自检脚本

```bash
# 确定性计算（禁止心算）
python scripts/pcbcalc.py --help
python scripts/pcbcalc.py trace --current 1.5 --rise 10 --layers 1 --copper 1oz
python scripts/pcbcalc.py divider --vin 5 --r1 10k --r2 20k
python scripts/pcbcalc.py thermal-ldo --vin 12 --vout 5 --iout 0.3 --rth 60
python scripts/pcbcalc.py battery --mah 2000 --ma 150
python scripts/pcbcalc.py rc --r 10k --c 100n

# net-table.csv ↔ 原理图网表 双向对账
python scripts/netlist_check.py net-table.csv netlist.csv

# BOM / CPL 一致性 + 位号冲突
python scripts/bom_check.py bom.csv cpl.csv

# 制造文件完整性
python scripts/release_audit.py <gerber目录> --bom bom.csv --cpl cpl.csv --json
```

## 2. 网表对账（Gate 3 放行）

`netlist_check.py` 输出三类差异：

- **仅 CSV 有**：设计意图连了但图里没连（或命名不一致）
- **仅网表有**：图里连了但 CSV 没记（漏记权威源）
- **同名不同脚**：网络名相同但成员不同（最危险，通常是复制粘贴错位）

必须 0 差异。差异先怀疑命名/位号，再怀疑真接错。

## 3. BOM/CPL 一致性（Gate 4 放行）

- BOM 与 CPL 的位号集合必须一致
- 不允许位号重复
- BOM 中每个器件都要有型号、封装；投贴片的还要有 LCSC C 号
- BOM 与原理图位号集合一致
- 数量按板数 + 备件核算

## 4. 制造文件放行（Gate 5）

| 文件 | 必须 |
|---|---|
|  Gerber 各层 | 顶层、底层、所有内层、阻焊、钢网（如贴片）、丝印 |
| 钻孔文件 | Excellon，含孔类型与尺寸 |
| 板框层 | 独立且被厂方识别 |
| BOM | 含位号/型号/封装/数量/C号 |
| CPL 坐标文件 | 位号/坐标/层/旋转，与 BOM 位号一致 |
| 叠层说明 | 层数与各层用途 |

放行前最后一步：**用独立的 Gerber 查看器打开导出的文件目视复核一遍**，
不要只看 EDA 里的视图。这是最后一道人工闸门。

## 5. go / no-go 判定

- **go**：DRC 全清、对账 0 差异、文件齐全、无 Critical/Major 未决项
- **conditional**：有 Minor 项，用户知情后可投
- **no-go**：有 Critical，或 DRC/对账未通过

`release_audit.py` 只做机械检查，最终结论由人下。报告必须列出
「必须人工复核项」。

## 6. 上电 bring-up

见 [templates/bringup-log.md](../templates/bringup-log.md)。顺序固定：

1. 限流电源或带保护的电池输入
2. 先量各电源轨，确认电压与顺序正确
3. 确认无异常发热、无冒烟、无异味
4. 再装贵重器件（MCU、模组）
5. 测时钟、复位、编程接口
6. 逐接口验证
7. 记录每一步的测量值

**严禁**：不量电源直接全装全上电。

## 7. 交付清单

```
/交付/
├─ gerber/            # 各层 + 钻孔
├─ bom.csv            # 物料清单
├─ cpl.csv            # 贴片坐标
├─ stackup.md         # 叠层说明
├─ net-table.csv      # 连接权威源
├─ release-report.json# release_audit.py 输出
└─ bringup-log.md     # 上电记录
```
