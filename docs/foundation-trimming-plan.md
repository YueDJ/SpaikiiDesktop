# Sparkii 底座裁剪方案（Foundation Trimming Plan）

目标：把当前 monorepo 裁成一个**工业级 Agent 底座**，核心只保留最基本的 Agent
能力，其余能力通过 **Skill / 插件 / MCP / 服务门控工具 / 独立前端** 承载。未来
的合同分析、标书评估、深度调研、企业 ontology + 向量库对接，全部落在这些边缘
通道上，而不是写进核心里。

本文档是**方法论 + 边界口径 + 落地顺序**。可执行的模块归属底稿见
[`foundation-phase0-import-scan.md`](foundation-phase0-import-scan.md)，扫描工具见
[`scripts/phase0_import_scan.py`](../scripts/phase0_import_scan.py)。

## 一、三条已确认的边界口径

1. **核心工具集收敛到约 9 个**：`terminal`、`read_file`、`write_file`/`patch`、
   `search_files`、`web_search`/`web_extract`、`todo`、`memory`、`delegate_task`、
   `clarify`。其余（浏览器、图像/视频生成、Home Assistant、Kanban、computer use、
   TTS、cron、desktop_ui、project、react_to_message 等）下沉为插件 / MCP /
   `check_fn` 门控工具。

2. **产品/消费层彻底移出底座**。账单、订阅、积分、入门向导、门户、宠物、curator、
   models_dev、monitoring/gateway_health、display/skin、i18n 等消费级代码不进入底座；
   底座不背任何商业产品逻辑。

3. **原地先翻正依赖、形成 `core` 包，再决定是否拆独立 repo**。不一开始就做大迁移；
   先把核心对表面的反向依赖归零，边界稳定后再评估拆包。

## 二、裁剪的科学方法：依赖分层 + 单向箭头

判断一个模块该不该留在底座，标准只有一条：

> 它是否被 Agent 内核依赖，且它自己不依赖任何表面层。

合法依赖方向**只有** `表面 → 核心`，绝不反向。裁剪的每一步都以"反向 import 归零"
为完成标志，而不是"删了多少目录"。

方法五原则：

1. **先建依赖图，不靠直觉**。用 import 扫描把边界写成机器可校验的事实（本文档配套
   的 `scripts/phase0_import_scan.py` 就是第一版）。
2. **箭头只允许一个方向**。`core` 禁止 import `gateway` / `sparkii_cli` / `cli`。
3. **先翻正，再删除**。反向依赖不是删掉，而是把核心需要的东西**迁进核心**、把核心
   不需要的东西**下沉成插件**。能力不消失，只是换位置。
4. **搁置而非摧毁**。视频生成、HA、Kanban 等要继续活着，只是不在核心工具集里。
5. **每一步有可验证的完成定义**。见第五节。

## 三、分层模型 S0–S7

| 层 | 内容 | 动作 |
|---|---|---|
| **S0 原子内核** | `tools/registry.py`、`sparkii_constants.py`、`utils.py`、`sparkii_time.py` 等零产品依赖的底层 | 保留；其中带表面依赖的需先"去 lint" |
| **S1 核心抽象（错放在 surface）** | `gateway/session_context.py`（ContextVar session 身份） | 迁入核心 |
| **S2 服务层（错放在 sparkii_cli）** | env_loader / timeouts / profiles / config / models / version / sqlite / mcp_config / tools_config / 凭据生命周期 | 剥离进核心 |
| **S3 Agent 内核** | conversation_loop、provider adapters、memory、compression/cache、budget、prompt_builder、tool_executor、error_classifier、retry | 保留在核心 |
| **S4 扩展基础设施** | 插件加载器、技能加载器、toolset 解析、MCP client、check_fn 门控 | 迁入核心（可定制的命脉） |
| **S5 边缘能力** | browser、image/video gen、HA、kanban、computer use、TTS、cron、desktop_ui、project、react_to_message、wake_word | 下沉为插件 / MCP / 门控工具 |
| **S6 产品/消费层** | billing/subscription/credits/onboarding/portal/pet/curator/models_dev/monitoring-gateway_health/display-skin/i18n | 移出底座 |
| **S7 前端** | cli.py + sparkii_cli 表现层、gateway + platforms、ui-tui + tui_gateway、apps/desktop + shared、website、acp_adapter | 独立 repo |

核心结论：**S0–S4 是底座，S5–S7 是被删除或迁出的部分**。但必须先让 S0–S4 自洽
（不 import S5–S7），S5–S7 才能被安全切掉。

## 四、落地顺序（顺序就是科学性）

1. **动 S1**：把 `gateway/session_context.py` 迁进核心，消掉 core→gateway 的第一类
   反向依赖，给后续步骤打样。
2. **动 S2**：把 `sparkii_cli` 的服务层剥离进核心，消除约 133 处 core→sparkii_cli
   反向 import。这是最大的一步。
3. **动 S4**：把插件/技能/MCP 加载器收进核心。这是"可定制"的保障。
4. **核心自洽后，动 S5**：`_SPARKII_CORE_TOOLS` 从 50+ 砍到约 9 个，其余下沉。
5. **动 S6、S7**：产品层和前端整体迁出；`cli.py`、`gateway/run.py`、`apps/`、
   `ui-tui/`、`website/` 变成叶子后整包迁移。

## 五、每一步的完成定义（DoD）

任何一步合入前必须同时满足：

- `scripts/phase0_import_scan.py` 报告中"反向 import"数量下降，且目标层归零；
- 对应测试通过（尤其对着临时 `SPARKII_HOME` 的 E2E，不靠绿色单测 mock）；
- 一个会话内 system prompt 字节稳定（prompt 缓存不因裁剪被破坏）；
- 表面能力仍是 session 的属性：GUI session 在 `SPARKII_DESKTOP` 为空的条件下仍能
  拿到 desktop 工具（不退回 env-var 门控）。

## 六、与未来应用的关系

未来四个应用全部落在四个既有缝上，裁剪就是把这四个缝打扫干净：

- **MCP 客户端**（`tools/mcp_tool.py` + `sparkii_cli/mcp_catalog.py`）→ 企业 ontology
  / 向量库走 MCP 对接；
- **插件加载器** → ontology/向量库做成 provider 插件（ABC + 编排）；
- **技能加载器** → 合同分析、标书评估、深度调研做成 Skill；
- **toolset 解析 + check_fn 门控** → 每个客户 profile 决定启用哪些能力，配了凭据
  才出现，不进核心 schema。

## 七、现状基线（2026-08-20 扫描）

| 指标 | 数值 |
|---|---|
| 核心文件总数 | 356 |
| 反向 import 表面包的文件数 | 139（39%） |
| 其中 import `gateway` | 27 |
| 其中 import `sparkii_cli` | 133 |
| 其中 import `cli` | 1 |

这些数字是裁剪的起点和进度计。详细归属与反向依赖清单见 Phase 0 文档。
