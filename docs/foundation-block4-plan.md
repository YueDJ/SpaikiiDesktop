# Block 4 迁移方案 — 前端独立 repo（2026-08-20）

> 对应 `docs/foundation-trim-status.md` 的 Block 4（S7 前端独立）。本文件先定
> **迁移边界**与**包结构**，再给出分步执行计划。每一步都有验证门槛
> （ast.parse → import → pytest → 扫描器数字下降）。

## 0. 结论摘要

- **推荐边界**：前端 repo 迁出 8 个顶层单元 —— `cli.py`、`sparkii_cli/`、
  `tui_gateway/`、`gateway/`、`acp_adapter/`、`ui-tui/`、`apps/`、`website/`
  及其测试。核心 repo 保留 agent/tools/providers/core/cron/plugins/scripts
  与内核顶层模块。
- **为什么比用户点名的 6 项多 2 项**：`cli.py` ↔ `sparkii_cli` ↔ `tui_gateway`
  是互相 import 的强耦合簇（证据见 §2.1）。只搬 `cli.py` 会在 core 包留下
  顶层 `import cli`（`tui_gateway/slash_worker.py:29`），边界不可成立。
- **依赖方向**：前端 → core 单向。core 包任何模块不得 import 前端 6+2 个单元。
- **包结构**：core repo 沿用包名 `sparkii-agent`（pip 兼容，去掉前端目录）；
  前端 repo 新包名 `sparkii-frontends`，声明 `sparkii-agent` 为依赖
  （开发期 path 依赖，发布期 git 依赖）。console scripts 拆分：
  `sparkii` / `sparkii-acp` 归前端，`sparkii-agent` 归 core。
- **执行分 6 步**：扫描（已完成）→ 核心侧解耦 → 共享服务下沉 → 前端 repo
  脚手架 → 物理迁移 → 依赖接线/测试/CI。当前处于 Step 1。

## 1. 数据基线（扫描日期 2026-08-20）

可复跑扫描器：

- `scripts/phase0_import_scan.py` — 窄核心（agent/tools/providers/core +
  顶层文件）→ surface（gateway/sparkii_cli/cli）。
- `scripts/phase0_block4_scan.py --csv` — Block 4 全量边界扫描（新增；
  csv 落 `docs/foundation-block4-scan.csv`）。

| 指标 | 值 |
|---|---|
| 移动面文件数（git 追踪） | cli.py 1、gateway 74、ui-tui 474、apps 1998、website 778、acp_adapter 11 |
| 窄核心 → surface（phase0） | **50**（gateway 9、sparkii_cli 43、cli 1） |
| core repo → 移动面（block4 扫描） | **44**（43 处 gateway + 2 处 acp_adapter，1 文件双中） |
| 测试 import gateway | 467 个文件 |
| 测试 import acp_adapter | 21 个文件 |

### 1.1 窄核心 → gateway（9 处，全部惰性）

`agent/relay_runtime.py`、`agent/system_prompt.py`、`tools/async_delegation.py`、
`tools/browser_tool.py`、`tools/environments/local.py`、`tools/mcp_tool.py`、
`tools/process_registry.py`、`tools/skills_tool.py`、`toolsets.py`。

### 1.2 core repo 其余 → gateway/acp（35 处）

- `sparkii_cli/`（23 个文件）：gateway 管理/状态/服务/更新/web_server/kanban 等。
- `tui_gateway/`（2 个文件）：`server.py`、`methods_session.py`。
- `cron/`（2 个文件）：`scheduler.py`（16+ 处）、`executions.py`（2 处）。
- `plugins/`（3 个文件）：google_meet、kanban/dashboard、memory/honcho。
- `scripts/`（2 个文件）：conformance 生成器、gateway health probe（dev 工具）。
- `model_tools.py` → `acp_adapter.edit_approval`（1 处）。
- `sparkii_cli/main.py` → `acp_adapter.entry`（1 处，随 sparkii_cli 迁走后自然消失）。

## 2. 迁移边界

### 2.1 为什么 `sparkii_cli/` 与 `tui_gateway/` 必须随迁

硬证据（顶层 import，无法惰性化）：

| 源（留 core 则非法） | import | 证据行 |
|---|---|---|
| tui_gateway → cli | `import cli as cli_mod` / `from cli import SparkiiCLI` | `tui_gateway/slash_worker.py:29-30` |
| tui_gateway → cli | `from cli import ...`（多处惰性） | `methods_prompt.py:871` 等 |
| sparkii_cli → cli | `from cli import CLI_CONFIG` / `ChatConsole` / ... | `callbacks.py:27`、`cli_agent_setup_mixin.py:34`、`commands.py:47` |
| cli → sparkii_cli | 大量（cli.py 是 sparkii_cli 的命令编排层） | cli.py 全文 |
| sparkii_cli → gateway | 23 个文件，gateway.py/web_server.py 为**顶层** import | `sparkii_cli/gateway.py:32-34` |
| tui_gateway → gateway | 3 处惰性 | `server.py:742` 等 |

若只搬 `cli.py`/`gateway/` 而把 sparkii_cli、tui_gateway 留在 core 包，core 包
必然出现顶层 `import cli` 与 23 个文件反向依赖 gateway —— 两个独立 repo 间
出现依赖环，包无法独立安装。因此边界必须把整簇一起迁出。

### 2.2 `cron/` 处理（推荐：留 core，反转交付）

`cron/scheduler.py` 是内核调度器（agent 侧 cron 工具也使用），但 16+ 处惰性
import `gateway.config/session/delivery/mirror/relay/response_filters/...`
（消息交付路径），5 处 import `sparkii_cli`（tools_config/plugins/auth/
runtime_provider/resource_limits）。处置：

- cron → sparkii_cli：Block 3 后多数已有 core 对应物（core.plugins、
  core.auth_store），剩余（runtime_provider/tools_config/resource_limits）
  走 Step 2 下沉后改 import core.*。
- cron → gateway 交付：定义注入钩子（`set_delivery_provider`、
  `set_session_source_provider`、`set_platform_registry_provider` 等），
  gateway/run.py 注册。此为 Step 2 中最大的一块，独立里程碑。
- 备选（不推荐）：cron 整体随迁，代价是 `tools/cronjob_tools.py`（core 工具）
  反向依赖前端，重新引入同一问题。

### 2.3 `plugins/` 与 `scripts/` 残留

- `plugins/google_meet/process_manager.py` → `gateway.status._pid_exists`：
  改 `core.process_utils`（Step 1 已做）。
- `plugins/kanban/dashboard/plugin_api.py`、`plugins/memory/honcho/cli.py`
  → `gateway.config.load_gateway_config`：改 `core.config.load_config_readonly`
  （配置读取无 gateway 运行时依赖）。
- `scripts/generate_conformance_vectors.py`、
  `scripts/observability/gateway_health_export_probe.py`：dev 工具，
  迁移时可随前端 repo 走或保持"允许跨 repo import"豁免，不进运行时包。

### 2.4 测试边界

按 `docs/foundation-block4-scan.csv` 的 `test_to_move` 边逐文件判定：

- 整目录随迁：`tests/gateway/`（400+）、`tests/acp/`、`tests/acp_adapter/`、
  `tests/cli/`、`tests/tui_gateway/`。
- 部分随迁：`tests/sparkii_cli/`（gateway/web_server/kanban/pairing 相关）、
  `tests/cron/`（交付相关）、`tests/tools/`（gateway 相关）、`tests/agent/`
  （relay 相关）、`tests/e2e/`。
- 改测试 patch 目标：核心侧解耦后，patch `gateway.status.*`/`gateway.platforms.base.*`
  的测试按既有约定改 `core.*`（§4 处置表列出）。

## 3. 包结构

### 3.1 core repo（包名沿用 `sparkii-agent`）

```
sparkii-agent/                    # 即本仓库去除前端 8 单元后的剩余
├── agent/  tools/  providers/  core/  cron/  plugins/  scripts/
├── run_agent.py  model_tools.py  toolsets.py  toolset_distributions.py
├── batch_runner.py  trajectory_compressor.py  registration_lifecycle.py
├── sparkii_state*.py  sparkii_constants.py  sparkii_logging.py
├── sparkii_time.py  utils.py  mcp_serve.py
├── pyproject.toml                # packages.find 移除前端目录
├── tests/                        # 核心相关测试
└── Dockerfile  nix/  .github/    # CI 只跑核心
```

### 3.2 前端 repo（新包名 `sparkii-frontends`）

```
sparkii-frontends/
├── pyproject.toml
│   # dependencies: sparkii-agent @ <git/path>
│   # [project.scripts] sparkii = "sparkii_cli.main:main"
│   #                   sparkii-acp = "acp_adapter.entry:main"
├── cli.py  sparkii_cli/  tui_gateway/  gateway/  acp_adapter/
├── ui-tui/  apps/  website/
├── package.json                    # workspaces: apps/*, ui-tui, ui-tui/packages/*
└── tests/                          # 随迁测试
```

### 3.3 依赖与接线

- Python：前端 pyproject 依赖 `sparkii-agent`。开发期用 path 依赖
  （`sparkii-agent @ file://../sparkii-agent`），发布期改 git 依赖
  （`sparkii-agent @ git+https://github.com/<org>/sparkii-agent.git@<tag>`）。
- npm：`@sparkii/shared` 位于 `apps/shared`（随迁）；ui-tui 对它的引用
  全部在移动面内，无跨 repo npm 依赖。core repo 不再保留 package.json 工作区。
- 运行时：desktop（apps/，随迁）spawn 的 `sparkii serve` 由前端 repo 的
  `sparkii_cli` 提供，依赖已安装的 core 包。`sparkii --tui` 同理。
- 入口拆分：`sparkii-agent`（run_agent）留 core；`sparkii`（CLI 全套）、
  `sparkii-acp` 归前端。`sparkii_bootstrap.py` 说明文字同步更新。

### 3.4 历史迁移

前端 repo 用 `git subtree split --prefix=<dir> main`（或 filter-repo）保留
各目录历史；先提交当前脏工作区（Block 2/3 未提交改动）再 split，避免丢失。

## 4. 耦合点处置清单

| 处置 | 含义 | 数量 |
|---|---|---|
| MOVE | 随迁后自然消失（前端内部依赖） | sparkii_cli/tui_gateway → gateway 全部、gateway → sparkii_cli/cli 全部 |
| EXTRACT | 函数/常量下沉 core，前端 re-export | gateway.status 进程助手、gateway.platforms.base 媒体缓存、sparkii_cli 共享服务 |
| INVERT | 注入钩子，前端注册 | platform_registry、ACP 编辑审批、gateway 配置读取、cron 交付、gateway running-pid |

### 4.1 Step 1 已/将处理（两种边界都必须做的核心侧解耦）

| 耦合点 | 处置 | 落地 |
|---|---|---|
| gateway.status：`_pid_exists`/`get_process_start_time`/`terminate_pid` | EXTRACT → `core/process_utils.py`，status.py re-export | Step 1 |
| gateway.restart：`is_gateway_supervisor_process` | EXTRACT → `core/process_utils.py`，restart.py re-export | Step 1 |
| gateway.status：`get_running_pid` | INVERT：`set_gateway_running_pid_provider()`，status.py 注册 | Step 1 |
| model_tools → `acp_adapter.edit_approval.maybe_require_edit_approval` | EXTRACT 契约 → `core/edit_approval.py`，acp_adapter re-export | Step 1 |
| toolsets / agent.system_prompt → `gateway.platform_registry` | INVERT：`core.plugins.get_platform_registry()` 公开访问器 | Step 1 |
| agent.relay_runtime → `gateway.run._load_gateway_config` | EXTRACT：改 `core.config.load_config_readonly` | Step 1 |
| tools.delegate_tool → `cli.CLI_CONFIG` | EXTRACT：改 `core.config` | Step 1 |
| tools.skills_tool → `gateway.platforms.base` 常量 | EXTRACT → `core/media_cache.py` | Step 1 |
| tools.mcp_tool → 媒体缓存 + `_pid_exists` | EXTRACT → `core/media_cache.py` + `core.process_utils` | Step 1/1b |
| cron.executions、plugins/google_meet → `gateway.status` | EXTRACT → `core.process_utils` | Step 1 |
| plugins/kanban、honcho → `gateway.config` | EXTRACT → `core.config` | Step 1 |

### 4.2 Step 2 下沉清单（sparkii_cli → core，按符号）

| sparkii_cli 模块 | 处置 |
|---|---|
| `__version__` | → `core.version`（3 处顶层引用） |
| `runtime_provider` | 下沉 core（agent/auxiliary_client、run_agent、model_tools 等 12+ 处） |
| `models` / `model_normalize` / `model_switch` | 下沉 core（chat_completion_helpers、agent_init 等） |
| `profiles` | 下沉 core（conversation_compression、system_prompt 等 10+ 处） |
| `tools_config` / `resource_limits` / `managed_uv` / `backup` / `prompt_size` | 下沉 core |
| `middleware` / `approval_transport` / `lifecycle` / `copilot_auth` | 下沉 core 或注入 |
| `goals` / `heartbeat` / `loops` / `kanban_db` / `projects_db` | 产品面，工具侧改注入 |
| `commands` / `display` / `main._AUX_TASKS` / `observability` | 已注入或随迁 |

> 完成标志：`scripts/phase0_import_scan.py` 中"core files offending"归零。

## 5. 执行步骤与验证门槛

| 步骤 | 内容 | 验证 |
|---|---|---|
| Step 0 | 扫描脚本 + 基线 csv | 已落盘 |
| Step 1 | 核心侧解耦（§4.1） | ✅ 已完成：ast.parse 全仓通过；phase0 gateway 9→0、cli 1→0（50→43）；block4 44→30；相关测试无新增失败 |
| Step 2 | sparkii_cli 共享服务下沉（§4.2） | ✅ 已完成：phase0 50→**0**；block4 30→**6**（cron/scheduler + 5 dev 脚本）；21 模块 + observability 包下沉 core，注入桥就位 |
| Step 2b | cron/scheduler.py 交付反转（gateway→注入钩子） | ✅ 已完成：20 处 gateway 引用 → core.cron_delivery 命名空间（gateway/__init__ 注册）；response_filters 下沉 core；block4 6→5（仅剩 dev 脚本） |
| Step 3 | 前端 repo 脚手架（新目录、pyproject、package.json） | ✅ 已完成：`C:\Users\YDJ\Desktop\sparkiidesktop-frontends`；双 editable 安装验证 `sparkii --help` / `sparkii-agent --help`；core phase0 0 |
| Step 4 | 物理迁移 + 测试随迁 + CI 拆分 | ✅ 已完成（物理迁移并入 Step 3，git archive 抽取而非 subtree；测试 186 文件随迁；core 删 8 个前端 workflow + 前端新增 tests/js-tests CI；前端已推送 origin） |
| Step 5 | 依赖接线 + 测试迁移 + CI 拆分 | 前端 pytest + vitest 绿；core pytest 绿 |
| Step 6 | Dockerfile/nix/文档/状态文档更新 | `docs/foundation-trim-status.md` 更新 Block 4 状态 |

测试命令（沿用状态文档）：

```bat
.venv\Scripts\python.exe -m pytest <paths> -q -p no:cacheprovider --basetemp=.pytest-tmp
.venv\Scripts\python.exe scripts\phase0_import_scan.py
.venv\Scripts\python.exe scripts\phase0_block4_scan.py --csv
```

## 6. 风险与坑

- 工作区脏：Block 2/3 有大量未提交改动，物理迁移前必须先提交（含删除/新增）。
- 测试 patch 目标：核心侧解耦后必须同步改 `gateway.*` → `core.*`
  （项目既有约定），否则核心工具看不到 mock。
- cron 交付反转是最大工作量（scheduler.py 6700+ 行），单独里程碑，
  不阻塞 Step 3 脚手架。
- Windows 坑：GBK 编码、`--basetemp=.pytest-tmp`、shutil.move 加
  `not dst.exists()` 守卫、写文件重试（Errno 22）。
- `_resolve_cache_dir` 依赖模块级常量 monkeypatch 语义：下沉后测试 patch
  目标须指向新模块（`core.media_cache.AUDIO_CACHE_DIR`）。
- 前端 repo 的 `sparkii` 入口依赖 core 包已安装；升级路径要在发布说明中
  写清"先装 core 再装 frontends"（或 frontends 声明依赖自动带出）。
