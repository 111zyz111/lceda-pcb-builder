# 嘉立创EDA专业版 MCP 操作手册（路径 A）

前置条件：本机装有 嘉立创EDA专业版 + 已加载桥接扩展（`.eext`）+ MCP 服务器已在 harness 中注册。
桥的作用是把 AI 的调用转成 `eda.*` API 在客户端执行。

## 0. 三条铁律

1. **多页面先选目标。** 任何读写前先 `bridge_clients` 确认当前有几个 EDA 页面，
   再 `bridge_select_client` 选定 clientId。多开页面时选错页面是静默错误的头号来源。
2. **写入必回读。** 每个写工具调用后，必须用对应读工具回读同一图元，
   核对 ID / 网络 / 几何。不一致 → 回滚 + 报告。
3. **`confirm:true` 不可滥用。** 仅对用户明确授权的结构性变更（建板、删页、改层数、
   批量删除）使用；禁止用 confirm 绕过不确定的改动。

## 1. 标准调用顺序

```
① bridge_clients            → 确认连接与目标页面
② bridge_select_client      → 锁定目标（多页面时）
③ project_info              → 读工程/板/原理图/PCB 身份与文档目录
④ schematic_read            → 读当前原理图完整语义快照
⑤ component_select          → 按规格或 LCSC C号搜器件，返回最多5个候选
⑥ component_place_auto      → 按坐标放置器件（已知坐标时优先）
⑦ netlabel_place            → 在引脚位置放网络标签实现连接（替代飞线）
⑧ schematic_drc_check       → 原理图 DRC，必须无 error
⑨ board_setup               → 建板并关联 PCB（需 confirm:true）
⑩ pcb_component_edit        → PCB 中放置/移动器件
⑪ pcb_board_outline_manage  → 板框（固定用层 11）
⑫ pcb_layer_manage          → 设铜层数（官方支持 2–32 偶数层）
⑬ pcb_region_manage         → 禁止/约束区域
⑭ pcb_connectivity_action   → 为指定网络创建直线/过孔
⑮ pcb_pour_manage           → 覆铜（创建边框 + 显式重建）
⑯ pcb_drc_check             → PCB DRC，必须无 error
⑰ manufacture_export        → 导出制造文件（Gerber/BOM/CPL）
```

## 2. 工具清单（58 个，按用途分组）

> 实际可用工具取决于桥的版本。以 `bridge_clients` + `api_index` 实际返回为准。

### 桥管理
`bridge_clients`、`bridge_select_client`、`bridge_recover_client`
（写超时/失联/提交未确认时用它恢复，先取 requestId，以 action=recover 执行）

### 读取
`project_info`、`schematic_read`、`pcb_read`、`footprint_read`、
`schematic_review`（全工程网表）、`pcb_net_query`、`pcb_layer_query`、
`pcb_constraints_query`、`schematic_pages_manage`（也含读）、
`eda_context`、`eda_canvas_snapshot`（渲染区截图，可作辅助但**不能替代回读**）

### 原理图写入
`component_place`（引导用户交互放置）、`component_place_auto`（按坐标/网格）、
`schematic_component_edit`、`schematic_wire_manage`、`schematic_text_manage`、
`schematic_connectivity_action`（安全预览/创建导线、NetPort）、
`netlabel_place`、`netlabel_modify`、`schematic_layout_check`、
`schematic_document_action`（坐标/选择/导航/保存/导入）

### 原理图自动化（BETA，结果必须人工复核）
`schematic_auto_layout`、`schematic_auto_routing`

### PCB 写入
`pcb_component_edit`、`pcb_routing_edit`、`pcb_connectivity_action`、
`pcb_pour_manage`、`pcb_board_outline_manage`、`pcb_region_manage`、
`pcb_text_manage`、`pcb_layer_manage`、`pcb_constraints_manage`、
`pcb_document_action`

### 检查
`schematic_drc_check`、`pcb_drc_check`、`pcb_realtime_drc`、
`netlist_compare`、`design_compare`、`schematic_layout_check`

### 器件与库
`component_select`、`library_search`、`library_sources`、
`library_classification_query`、`library_preview`（渲染符号/封装供目检）

### 工程结构
`board_setup`、`pcb_documents_manage`、`schematic_pages_manage`、`editor_navigate`

### 制造输出
`manufacture_export`、`manufacture_templates_query`、
`design_archive_export`、`design_source_export`、`workspace_query`

## 3. 已知参数陷阱

| 陷阱 | 说明 | 应对 |
|---|---|---|
| **裸器件引用** | `component_place_auto` 传裸引用会先解析为完整库对象；解析不到返回 `DEVICE_NOT_FOUND`，且**不会**调用原生创建 | 先用 `component_select` / `library_search` 拿完整引用 |
| **网络标签的 EDA 版本差异** | 电源/地网络标识可用；**普通网络标签需要 EDA v4**，3.x 直接报不支持 | 先 `eda_context` 查版本；低版本改用导线连接 |
| **板框固定层** | 新建板框固定用层 11、空网络；回读可能为 null | 用 `pcb_board_outline_manage` 回读确认，不要假设 |
| **闭合轮廓绕序** | 创建/修改覆铜与区域时，闭合轮廓接受反向绕序与循环起点变化，原生坐标会归一化到四位小数 | 回读比对归一化结果，不要按原始输入逐字符比较 |
| **多点轮廓** | `pcb_region_manage` 的创建/修改**仅接受单轮廓**；多点轮廓须在末尾重复首点显式闭合 | 构造数据时末尾补首点 |
| **文字对齐不可写** | `schematic_text_manage` 修改已有文字会破坏对齐方式，故不提供 modify；`alignMode` 只回读 | 改文字内容用 create 新 + delete 旧，或接受对齐损失 |
| **Attribute 不可直写** | PCB 器件属性无法通过官方 API 直接改 | 走 `pcb_text_manage` 的 Attribute 通道或让用户在界面改 |
| **降层阻挡** | `pcb_layer_manage` 降铜层数时，若待移除内层已有图元，返回阻挡图元且**不执行** | 先清空内层图元 |
| **零重叠副本** | `component_place_auto` 的精确重叠副本会回读后清理 | 回读确认位号未被 EDA 改写 |
| **分页 DRC** | `pcb_drc_check` 详情按 offset/limit 全局分页，用 `nextOffset` 续读 | 不要只看第一页就下结论 |
| **NC 引脚** | 不连接的引脚应显式标 NC 或放置 no-connect，不要留空 | Gate 3 对账时检查 |

## 4. 回读对账范式

每次写操作后固定三步：

```
1. 用对应读工具读回同一图元/网络/器件
2. 逐项核对：图元 ID 是否一致、网络名是否一致、几何是否在容差内、位号是否被改写
3. 不一致 → 记录差异 → 能修则修，不能修则回滚并列入「需人工决策」
```

`design_compare` / `netlist_compare` 可做原理图↔PCB↔网表的整体对账，
但它们是**辅助**，不能替代逐图元回读。

## 5. 桥的选择与降级

本机当前可能装有不同桥。若某个工具不存在：

1. 先用 `api_index` / `api_search` / `api_invoke` 直接调用 `eda.*` API 兜底
   （`api_invoke` 接受 JS 代码，是最通用的逃生口）
2. 仍不行则告知用户缺哪个工具，建议换桥
3. 换桥候选（按认可度）：
   - `zhoushoujianwork/easyeda-agent`（685★，MIT，CLI/Skill/MCP 三形态）
   - `hyl64/jlcmcp`（254★，MIT，59 工具，基于官方 Run API Gateway）
   - 官方 `easyeda/easyeda-api-skill`（921★，**无 LICENSE**，仅作 API 资料参考）

> 社区桥（如 `hs150521/JLCEDA-MCP-Community`，9★）自述非官方 release，属单点风险。
> 在 Skill 层把工具调用写成「意图 → 工具」的抽象，便于换桥。

## 6. 与官方扩展开发的关系

若需要写自己的 EDA 插件（`eda.*` API 不够用时），用官方
`easyeda/easyeda-api-sdk`（Apache-2.0）。此路径只在用户明确要求扩展开发时启用。
