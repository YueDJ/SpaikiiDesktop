# Phase 0 — 可执行底稿（Import 扫描 + S0–S7 模块归属）

这是底座裁剪的第一份可执行底稿。数据来自
[`scripts/phase0_import_scan.py`](../scripts/phase0_import_scan.py)，可随时复跑：

```powershell
.venv\Scripts\python.exe scripts\phase0_import_scan.py
```

## 一、基线扫描结果

| 指标 | 数值 |
|---|---|
| 核心文件总数（agent/ + tools/ + providers/ + 顶层核心 .py） | 356 |
| 反向 import 表面包的文件数 | 139（39%） |
| 其中 import `gateway` | 27 |
| 其中 import `sparkii_cli` | 133 |
| 其中 import `cli` | 1 |

解读：**核心对表面的耦合面主要不是 `gateway`，而是 `sparkii_cli`**（133 处）。原因是
`sparkii_cli` 现在既是"服务层"（核心真正需要）又是"CLI 表现层"（纯表面）。所以 Phase 0
的最大工程量是**把服务层从 `sparkii_cli` 剥出来**，而不是先动 gateway。

### S1 完成记录（2026-08-20）

`gateway/session_context.py`（436 行，纯 stdlib 叶子模块）已迁入
[`core/session_context.py`](../core/session_context.py)，原路径保留为 4 行 re-export shim
（[`gateway/session_context.py`](../gateway/session_context.py)）。全仓 96 处 import 行、
59 个文件由 `gateway.session_context` 改写为 `core.session_context`，迁移脚本
[`scripts/phase0_s1_rewrite_imports.py`](../scripts/phase0_s1_rewrite_imports.py) 可复跑、
幂等。

验证：`core.session_context` 正常导入；shim 的 `get_session_env` / `set_session_vars`
与核心是同一对象。基线随之变化：

| 指标 | 改前 | 改后（S1 后） |
|---|---|---|
| 核心文件数 | 356 | 358 |
| 反向 import 总数 | 139 | 136 |
| import `gateway` | 27 | **11** |
| import `sparkii_cli` | 133 | 133（未动，S2 处理） |

剩余的 11 处 `gateway` import 是其他网关子模块（platform_registry / config / session /
delivery / hooks / relay 等），属于后续步骤或真正的表面依赖，不是 S1 的目标。

### S2a 完成记录（2026-08-20）

迁移脚本 [`scripts/phase0_s2_analyze.py`](../scripts/phase0_s2_analyze.py) 的依赖分析揭示：
原定的 21 个 S2 服务文件并非全部干净。**10 个是纯 stdlib 叶子**（零 sparkii_cli / agent /
gateway 依赖），已迁入 `core/`：`build_info`、`codex_models`、`config_defaults`、
`fallback_config`、`route_identity`、`sqlite_runtime`、`sqlite_safe_read`、`sqlite_util`、
`timefmt`、`toolset_validation`。原路径保留 re-export shim，84 处 import 行、46 个文件
由 `sparkii_cli.<name>` 改写为 `core.<name>`，残留 0。

**重要结论：** 头号指标 `import sparkii_cli`（133）在 S2a 后**不变**。原因是这些叶子被
import 的文件同时也 import 了纠缠簇（`config` / `models` / `auth` / `plugins` 等），文件
粒度的反向依赖并未消除。真正的削减在 S2b。

### S2b 关键发现：服务层与表面层互相纠缠

`sparkii_cli` 的"服务层"和"表面层"在文件粒度上不可干净切分，被核心依赖最重的几个服务
文件自身反向依赖了表面层：

- `config.py`（89 个核心文件依赖它）→ 反向 import `auth`、`colors`、`default_soul`、
  `personality`、`secret_prompt`、`mcp_security`、`managed_scope`；
- `models.py`（9）与 `runtime_provider.py`（11）→ `auth`、`providers`、`copilot_auth`、
  `moa_config`、`model_search`、`model_switch`、`nous_account`、`urllib_security`；
- `tools_config.py`（3）→ `cli_output`、`curses_ui`、`colors`、`inventory`、`managed_uv`、
  `nous_subscription`、`plugins`、`setup` 等一整套 CLI UI；
- `credential_lifecycle.py` → `auth`；`env_loader.py` → `_early_recovery`、`managed_scope`；
  `profiles.py` → `default_soul`、`gateway`、`service_manager`；`config_migrations.py` →
  `personality`；`model_catalog.py` → `__version__`。

**S2b 不是机械搬文件**，而是"重新切桶"：把核心真正需要的 `config + models +
runtime_provider + auth + providers + plugins + urllib_security + personality +
default_soul + moa_config + model_search + model_switch + lifecycle + middleware +
_subprocess_compat` 收敛进 `core`，同时把纯 UI/产品表面（`cli_output`、`curses_ui`、
`colors`、`skin_engine`、`banner`、`completion`、`web_server`、`dashboard`、
`nous_billing`、`portal`、`setup`、`inventory`）留在 `sparkii_cli`。交叉点需要逐处解耦
（例如 `config.py` 对 `colors`/`cli_output` 的消息染色依赖、对 `auth` 的取 key 依赖）。

### S2b 进展记录（2026-08-20）

先对 `config.py`（89 个核心文件依赖的 lynchpin）逐条削表面依赖。`config.py` 原有 7 条
表面依赖，已消除 5 条：

- `colors`、`default_soul`、`mcp_security`、`personality`、`secret_prompt` → 迁入
  `core/`（均为纯 stdlib 叶子），迁移脚本见
  [`scripts/phase0_s2b_move_colors.py`](../scripts/phase0_s2b_move_colors.py) 与
  [`scripts/phase0_s2b_move_leaf_edges.py`](../scripts/phase0_s2b_move_leaf_edges.py)；
- 验证：`sparkii_cli.config` 全依赖图导入通过，`core.*` 各模块导入通过，残留 import 为 0。

`config.py` 剩余表面依赖 2 条 + S2 依赖 2 条：

- `auth.get_anthropic_key`（lazy）——最后一条真正纠缠的表面依赖；
- `managed_scope`（lazy，且反向懒加载 `config._deep_merge/_expand_env_vars`）——与 config
  同源，应随 config 一起迁；
- `config_migrations`、`credential_lifecycle`（S2，各自仍依赖 `auth`）。

**后续执行（已推进）：** `get_anthropic_key` 只在 `show_config()`（纯展示函数）里用一次，
已内联为用 `get_env_value_prefer_dotenv` 查 `ANTHROPIC_API_KEY → ANTHROPIC_TOKEN →
CLAUDE_CODE_OAUTH_TOKEN`，从而切断 `config → auth` 这条边。现在 `config.py` 的剩余
`sparkii_cli` 依赖只有三条 config-adjacent：`config_migrations`、`credential_lifecycle`、
`managed_scope`。

下一步是抽离 `auth.py` 里真正属于核心的部分（`PROVIDER_REGISTRY` 这一 provider 元数据 +
`_load_auth_store`/`_save_auth_store`/`_auth_store_lock` 这套 credential 持久化原语 +
`suppress/unsuppress_credential_source`），把 OAuth 登录/令牌交换留在表面。做完后即可把
`config + config_migrations + credential_lifecycle + managed_scope` 作为一组迁入 `core`——
这一步落地后，133 才会第一次大幅下降（config.py 的 89 个依赖者全部改指 `core.config`）。

### auth.py 核心再切桶地图（已勘察）

`auth.py`（8271 行）里 `credential_lifecycle` 真正依赖的核心部分不是叶子，而是三个集群：

1. **provider 元数据**（~360 行）：`ProviderConfig`（dataclass）+ `PROVIDER_REGISTRY`
   （`Dict[str, ProviderConfig]`，含全部 provider 的 `api_key_env_vars`/base URL）+ 顶部
   一批 OAuth 常量（`DEFAULT_*_BASE_URL`、client_id、scope）+ 末尾的插件 provider 动态
   注册循环；
2. **credential 持久化原语**（~300 行，跨 1038–1340 与 2280）：`AUTH_STORE_VERSION`、
   `AUTH_LOCK_TIMEOUT_SECONDS`、`_auth_file_path`、`_auth_lock_path`、
   `_auth_lock_holder_for`、`_file_lock`（fcntl/msvcrt 跨进程文件锁）、`_auth_store_lock`、
   `_load_auth_store`、`_save_auth_store`、`_migrate_stale_nous_portal_url`；
3. **credential 源开关**：`suppress_credential_source` / `unsuppress_credential_source`。

这三块应迁入 `core/`（例如 `core/provider_registry.py`、`core/auth_store.py`、
`core/credential_sources.py`），auth.py 里 OAuth 登录/设备码/令牌刷新则留在表面。迁移时
用"verbatim 搬移 + auth.py 顶部 re-export shim"保持兼容，`credential_lifecycle` 改指
`core.*`。

**集群 #2 已落地（auth-store）：** 15 个符号（`AUTH_STORE_VERSION`、
`AUTH_LOCK_TIMEOUT_SECONDS`、`DEFAULT_NOUS_PORTAL_URL`、`_NOUS_STALE_PORTAL_HOSTS`、
`_auth_file_path`、`_auth_lock_path`、`_same_path`、`_auth_lock_holder_for`、
`_file_lock`、`_auth_store_lock`、`_load_auth_store`、`_save_auth_store`、
`_migrate_stale_nous_portal_url`、`_auth_target_lock_holders` 及其 guard）verbatim 迁入
[`core/auth_store.py`](../core/auth_store.py)（294 行），auth.py 顶部 re-export 保持兼容，
`credential_lifecycle` 的持久化函数 import 已改指 `core.auth_store`。验证：
`core.auth_store` / `sparkii_cli.auth` / `sparkii_cli.credential_lifecycle` /
`sparkii_cli.config` 全链路导入通过。迁移脚本见
[`scripts/phase0_s2b_extract_auth_store.py`](../scripts/phase0_s2b_extract_auth_store.py)。

**集群 #3 已落地（credential 源开关）：** `suppress_credential_source`、
`is_source_suppressed`、`unsuppress_credential_source` 三个函数 verbatim 迁入
[`core/credential_sources.py`](../core/credential_sources.py)（只依赖 `core.auth_store`），
auth.py re-export 保持兼容，`credential_lifecycle` 的 suppress/unsuppress import 已改指
`core.credential_sources`。迁移脚本见
[`scripts/phase0_s2b_extract_credential_sources.py`](../scripts/phase0_s2b_extract_credential_sources.py)。

至此 `credential_lifecycle → auth` 只剩最后一条依赖：`PROVIDER_REGISTRY`（provider 元数据）。

**集群 #1 已落地（provider 元数据）：** `ProviderConfig` + `PROVIDER_REGISTRY`（57
providers）+ 插件动态注册循环 + 19 个被引用的 OAuth/base-URL 常量（传递闭包确定），迁入
[`core/provider_registry.py`](../core/provider_registry.py)（384 行）。auth.py 顶部
re-export 保持兼容。迁移脚本见
[`scripts/phase0_s2b_extract_provider_registry.py`](../scripts/phase0_s2b_extract_provider_registry.py)。

至此 **auth.py 的核心再切桶全部完成**（auth_store / credential_sources /
provider_registry 三簇），`credential_lifecycle` 对 `sparkii_cli.auth` 的依赖已归零。

### S2c 完成记录（config 组迁核，2026-08-20）

`config`、`config_migrations`、`credential_lifecycle`、`managed_scope` 四个模块作为一组迁入
`core/`（它们互相引用，必须同迁）。迁移脚本
[`scripts/phase0_s2c_move_config_group.py`](../scripts/phase0_s2c_move_config_group.py) 重写
1119 处 import 行、402 个文件；[`scripts/phase0_s2c_fix_patch_targets.py`](../scripts/phase0_s2c_fix_patch_targets.py)
随后把 110 个测试文件里的 441 处 mock patch 目标（`patch("sparkii_cli.config.X")` 等）及
注释改为 `core.*`——否则 patch 会打在 shim 上而失效。

**头号指标首次大幅下降：`import sparkii_cli` 133 → 95**（config.py 的 89 个依赖者中，
只依赖 config 的那批已改指 `core.config`；其余仍依赖 models/auth/plugins 等未迁模块）。
`import gateway` 仍为 11（未动）。

**唯一保留的临时边：** `core/credential_lifecycle.py` 中一处懒加载 + try/except 的
`from sparkii_cli.models import clear_provider_models_cache`（清 provider 模型缓存，尽力而为）。
该函数与 models.py 的 Ollama 探测缓存耦合，暂无法单独抽出，待 models 迁核时一并反转。

### 验证（pytest，2026-08-20）

已安装 `pytest==9.1.1` + `pytest-asyncio==1.3.0` 到 `.venv`。跑法（把临时目录指到工作区
内，规避沙箱对 `%TEMP%` 的限制）：

```powershell
.venv\Scripts\python.exe -m pytest <paths> -q -p no:cacheprovider --basetemp=.pytest-tmp
```

auth/config/provider 相关测试：**146 passed, 4 skipped, 1 failed**。唯一失败
`test_auth_remove_codex_migrates_legacy_dict_suppression` 是**既有失败**（该 fork 中
legacy dict 格式的 `suppressed_sources` 迁移逻辑缺失，`git show HEAD` 确认非本次引入）。
另有 3 个 `tests/gateway/test_session_env.py` 失败同为既有（`Platform.TELEGRAM = None`，
消息平台已在此 fork 退役）。

config 组迁移后：`test_config_loader_e2e` + `test_managed_scope` +
`test_credential_lifecycle` + `test_auxiliary_client`（182）+ `test_models`（79）共
**267 passed**。`test_config.py` 里 9 个失败为既有环境问题（中文 Windows 的 GBK 默认编码
读 UTF-8 文件 + 1 个 `~/.sparkii` 与 `AppData/Local/sparkii` 的 Windows 路径差异）。

### models.py 核心抽取的结论（S2d 尝试后回退，2026-08-20）

尝试从 `models.py`（6485 行）抽"纯模型解析"到 `core` 时，依赖闭包分析发现：

- `normalize_provider` 本身是纯的（只依赖 `_PROVIDER_ALIASES` 常量）；
- 但 `clear_provider_models_cache` 等缓存原语引用了 Ollama 进程内缓存，`cached_provider_model_ids`
  又调用 `provider_model_ids`（网络），闭包一算即连带 100+ 函数、触达 auth/providers/pricing；
- 核心文件里对 `fetch_models_with_pricing`、`get_nous_recommended_aux_model`、
  `copilot_default_headers` 等 15 个符号的依赖，大部分是"核心反向依赖集成/产品层"。

**结论：models.py 不能整迁，也暂不能廉价抽缓存簇。** 只 `normalize_provider` 可干净迁，
但其体量小、且不改变反向依赖计数。本次抽取已**回退**到 config 组迁移后的干净状态
（`import sparkii_cli` = 95）。models.py 的正确拆法留作后续专项：先做一次以
`normalize_provider` + `detect_provider_for_model` 为界的精确闭包，把网络/定价/产品层
依赖以门控或依赖反转处理，再拆 `core/model_resolution.py`。

### models.py 精确闭包底稿（专项第一稿，2026-08-20）

精确闭包结果（脚本内联计算）：

| 种子函数 | 闭包规模 | 表面 import 依赖 |
|---|---|---|
| `normalize_provider` | 2（+`_PROVIDER_ALIASES`） | **无** |
| `provider_group_for_slug` | 3 | **无** |
| `get_default_model_for_provider` | 13 | `model_catalog`、`models_dev` |
| `detect_static_provider_for_model` | 26 | `model_catalog`、`model_switch`、`models_dev` |
| `detect_provider_for_model` | 37 | 同上 |

detect 簇的 4 个表面触点（精确到符号）：

- `sparkii_cli.model_switch.MODEL_ALIASES`（常量 dict）
- `sparkii_cli.model_catalog.get_default_model_from_cache`（缓存读）
- `sparkii_cli.model_catalog.get_curated_openrouter_models`（**网络抓取，唯一硬依赖**）
- `agent.models_dev._load_disk_cache`（磁盘缓存读）

**拆分顺序：**

1. **M1（现在可做）**：`normalize_provider` + `_PROVIDER_ALIASES` +
   `provider_group_for_slug` + `group_providers` + `_SLUG_TO_GROUP` + `_PROVIDER_GROUPS`
   迁入 `core/model_resolution.py`（0 表面依赖）。
2. **M2（依赖反转）**：把 `MODEL_ALIASES`、`get_default_model_from_cache`、
   `_load_disk_cache` 作为常量/原语迁 core；把 `get_curated_openrouter_models` 改为
   注入式 callable（网络抓取留在 surface，由核心通过接口调用）。
3. **M3**：`detect_provider_for_model` + `detect_static_provider_for_model` +
   `get_default_model_for_provider` + `_resolve_static_model_alias` 等 37 符号迁入
   `core/model_resolution.py`。

**M1 已落地（2026-08-20）：** `normalize_provider`、`_PROVIDER_ALIASES`、
`provider_group_for_slug`、`group_providers`、`_SLUG_TO_GROUP`、`PROVIDER_GROUPS` 共
6 个符号迁入 [`core/model_resolution.py`](../core/model_resolution.py)（0 表面依赖），
相关 import 已改指 core。迁移脚本
[`scripts/phase0_m1_extract_model_resolution.py`](../scripts/phase0_m1_extract_model_resolution.py)。
验证：`test_models` + `test_model_switch_custom_providers` + `test_auxiliary_client`
**327 passed**（仅 2 个既有 GBK 失败）。`import sparkii_cli` 95 → 94。

**M2/M3 终止（前提被证伪）：** 进一步核实发现 `detect_provider_for_model` 只被
`sparkii_cli/oneshot.py` 和 `acp_adapter/server.py` 两个**表面层** import，核心
（agent/tools/providers/core）并不 import detect 簇的任何一个符号。也就是说 detect 簇是
**模型选择器（CLI/dashboard）的表面逻辑**，不是核心；把它迁入 `core` 反而违反窄腰原则。
同理 pricing / Nous / Copilot / DeepInfra / LM Studio / Ollama 这些核心文件里 import 的
models 符号，本质是"核心反向依赖了集成/产品层"，应在后续专项里做**依赖反转/门控**，而不是
迁入 core。

**结论：models.py 的核心抽取已完成。** 它唯一真正属于核心的 `normalize_provider` +
provider 分组已迁入 `core/model_resolution.py`；其余（detect、fetch、pricing、产品）留在
表面层是正确边界。

**迁移过程中的已知坑（已修复）：** ① Python 3.12 ast 的 `FunctionDef/ClassDef.lineno`
不含装饰器行，抽取时 `@dataclass`/`@contextmanager` 会遗漏，需手工补回；② `_file_lock`
依赖 `fcntl`/`msvcrt`（平台条件导入），需随迁；③ `apply_patch` 对 `try:` 块内 import 的
缩进可能打平，需逐处校验。

### 自动分层结果（规则化分类 + 人工复核，2026-08-20）

356 个核心文件的全量归属已写入
[`foundation-phase0-strata.csv`](foundation-phase0-strata.csv)，汇总如下：

| 层 | 文件数 | 处置 |
|---|---|---|
| S0 原子内核 | 5 | 保留；其中 4 个当前 import surface，需"去 lint" |
| S3 Agent 内核 | 192 | 保留（默认归核，MEDIUM 置信） |
| S4 扩展基础设施 | 30 | 迁入核心 |
| S5 边缘能力 | 83 | 下沉为插件 / MCP / 门控工具 |
| S6 产品/消费层 | 46 | 移出底座 |

错放在 surface 包、需要"迁入核心"的文件：

| 层 | 文件数 | 内容 |
|---|---|---|
| S1 | 1 | `gateway/session_context.py` |
| S2 | 21 | `sparkii_cli` 服务层 |
| S4 | 9 | `sparkii_cli` 插件/技能/MCP 加载器 |

**本轮人工复核修正了 6 处脚本初判**（已固化回扫描器规则）：

- `agent/battery.py`：S3 → **S6**（CLI/TUI 状态栏电池显示，产品层）
- `tools/blueprints.py`：S3 → **S5**（蓝图自动化，边缘能力）
- `tools/tool_search.py`：S3 → **S4**（MCP/插件渐进式披露，扩展设施）
- `tools/osv_check.py`：S3 → **S4**（MCP 包安全校验，扩展设施）
- `sparkii_cli/secrets_cli.py`：S2 → **S7**（`secrets` 子命令，CLI 表面）
- `sparkii_cli/model_cost_guard.py`、`model_data_policy_guard.py`、
  `model_selection_guards.py`：S2 → **S7**（模型选择 UX 守卫，表面）

## 二、扫描工具的口径

- **core** 定义为 `agent/`、`tools/`、`providers/` 三个目录 + 顶层 16 个核心 `.py`。
- **surface** 定义为 `gateway`、`sparkii_cli`、`cli` 三个包（这是当前实测的三类反向依赖）。
- **TOP** = 顶层无条件 import（硬依赖，优先修）；**nested** = 函数内/lazy/`TYPE_CHECKING`
  import（软依赖，次优先）。
- 扫描跳过 tests、node_modules、venv、dist、build、website、evals 等非源码目录。

## 三、S0–S7 模块归属底稿（已确认）

import 方向由扫描给出，语义归类经本轮人工复核。文件级全量清单见
[`foundation-phase0-strata.csv`](foundation-phase0-strata.csv)，以下按层给出关键文件。

### S0 原子内核（应零表面依赖）

真正已干净的文件：`tools/registry.py`、`batch_runner.py`、`registration_lifecycle.py`、
`sparkii_state_common.py`、`sparkii_state_portability.py`、`sparkii_state_schema.py`、
`sparkii_state_search.py`、`toolset_distributions.py`。

**需要"去 lint"的 S0**（属于核心但当前 import 了表面包）：`sparkii_constants.py`、
`sparkii_logging.py`、`sparkii_time.py`、`utils.py`——它们大多只是懒加载 `sparkii_cli`
拿配置/版本/时间格式，属于"核心需要的东西错放在表面"，按 S2 一起翻正。

### S1 核心抽象（错放在 surface，迁入核心）

- `gateway/session_context.py` —— `contextvars.ContextVar` 实现的 session 身份
  （platform / source / thread_id / user_id / chat_id）。这是核心概念，必须进核心。

### S2 服务层（错放在 sparkii_cli，剥离进核心）

最终确认 21 个（见上表）。按职责分组：

- 环境与密钥加载：`env_loader.py`
- 超时与时间：`timeouts.py`、`timefmt.py`
- 配置：`config.py`、`config_defaults.py`、`config_migrations.py`
- Profile：`profiles.py`
- 模型解析：`models.py`、`model_catalog.py`、`model_normalize.py`、`codex_models.py`、
  `fallback_config.py`
- 版本：`build_info.py`
- SQLite 原语：`sqlite_runtime.py`、`sqlite_util.py`、`sqlite_safe_read.py`
- MCP 配置与目录：`mcp_config.py`、`mcp_catalog.py`（同时属 S4）
- 工具/工具集配置：`tools_config.py`、`toolset_validation.py`
- 凭据生命周期：`credential_lifecycle.py`
- 路由与运行时：`route_identity.py`、`runtime_provider.py`

注意：`secrets_cli.py` 和 `model_{cost,data_policy,selection}_guards.py` 已确认是 CLI
表面层（S7），不在迁核清单里。

### S3 Agent 内核（保留）

`agent/conversation_loop.py`、各 provider adapter（`chat_completion_helpers.py`、
`codex_responses_adapter.py`、`anthropic_adapter.py`、`gemini_*`、`vertex_adapter.py`、
`bedrock_adapter.py` 等）、`memory_manager.py` / `memory_provider.py`、
`context_compressor.py` / `conversation_compression.py`、`iteration_budget.py`、
`prompt_builder.py`、`tool_executor.py`、`tool_dispatch_helpers.py`、
`error_classifier.py`、`retry_utils.py`、`message_*`、`usage_pricing.py` 等。

### S4 扩展基础设施（迁入核心）

- 插件加载：`sparkii_cli/plugins.py`、`sparkii_cli/agent_plugins.py`、`plugin_*`
- 技能加载：`agent/skill_commands.py`、`agent/skill_utils.py`、`agent/skill_bundles.py`、
  `tools/skills_tool.py`、`tools/skill_manager_tool.py`
- MCP：`tools/mcp_tool.py`、`tools/mcp_schema_cache.py`、`tools/mcp_oauth*.py`
- 工具注册/工具集解析：`tools/registry.py`、`toolsets.py`、`toolset_distributions.py`

### S5 边缘能力（下沉为插件 / MCP / 门控工具）

`tools/browser_*`、`tools/image_generation_tool.py`、`tools/video_generation_tool.py`、
`tools/flux3_video_tool.py`、`tools/xai_video_tools.py`、`tools/homeassistant_tool.py`、
`tools/kanban_tools.py`、`tools/cronjob_tools.py`、`tools/tts_tool.py`、
`tools/transcription_tools.py`、`tools/computer_use/`、`tools/desktop_ui.py`、
`tools/project_tools.py`、`tools/react_to_message_tool.py`、`tools/wake_word.py`、
`tools/voice_mode.py`、`tools/feishu_*`、`tools/microsoft_graph_*`。

这些正是 `_SPARKII_CORE_TOOLS` 要从 50+ 收缩掉的部分。

### S6 产品/消费层（移出底座）

`agent/billing_*`、`agent/subscription_view.py`、`agent/credits_tracker.py`、
`agent/onboarding.py`、`agent/portal_tags.py`、`agent/curator.py` / `curator_backup.py`、
`agent/models_dev.py`、`agent/pet/`、`agent/monitoring/`、`agent/display.py`、
`agent/i18n.py`、`agent/account_usage.py`、`agent/aux_accounting.py`、
`sparkii_cli/nous_billing.py`、`nous_subscription.py`、`portal_cli.py` 等。

### S7 前端（独立 repo）

`cli.py` + `sparkii_cli/` 表现层、`gateway/` + `gateway/platforms/`、`ui-tui/` +
`tui_gateway/`、`apps/desktop/` + `apps/shared/`、`website/`、`acp_adapter/`。

## 四、反向依赖清单（要修的东西）

共 139 个核心文件反向 import 了表面包。全量清单以扫描输出为准，这里给出硬依赖
（TOP，无条件 import）的分布规律：

- **`gateway` 的硬依赖很少**，且集中在两个本质上是"session 表面能力"的工具
  （`tools/desktop_ui.py`、`tools/react_to_message_tool.py`），属于 S5，随下沉自然消解。
- **`sparkii_cli` 的硬依赖最多**，散布在 `agent/` 和 `tools/`，根源是 S2 服务层没剥出来。
  先完成 S2 翻正，这一数字会大幅回落。

## 五、Phase 0 可执行步骤（按顺序）

1. **跑基线扫描并留档**：记录 356 / 139 / 27 / 133 / 1 作为进度计。
2. **确认 S0–S7 归属**：把本底稿的每个文件过一遍，把"猜测"变成"已确认"，产出最终归属表。
3. **切 S1**：`gateway/session_context.py` 迁入核心包，改 import，跑扫描确认 gateway 硬依赖归零。
4. **切 S2**：把 `sparkii_cli` 服务层文件迁入核心包，核心代码改 import，`sparkii_cli`
   反向依赖大降到只剩真正的前端调用。
5. **切 S4**：插件/技能/MCP 加载器收进核心，验证"可定制"机制不再依赖 CLI 包。
6. **每一步都复跑扫描**，反向 import 数量只降不升；完成后进入 Phase 1（收缩工具集）。

## 六、完成标准

- `scripts/phase0_import_scan.py` 中 `core files offending` 归零（或只剩明确豁免项）；
- 核心包对 `gateway` / `sparkii_cli` / `cli` 的 import 全部消失；
- 测试通过（尤其临时 `SPARKII_HOME` 的 E2E）；
- 一个会话内 system prompt 字节稳定，prompt 缓存不破坏。


### Phase A 进展（叶子级服务迁核，2026-08-20）

三向分流里的“继续迁 core”主线，先把核心依赖、自身几乎零表面依赖的叶子级服务迁入 core：

- 纯叶子（0 表面依赖）：_subprocess_compat、urllib_security、timeouts、sizefmt、
  dep_ensure、mem_trim、moa_config、model_search；
- env_loader（依赖反转）：唯一表面依赖是 _early_recovery._should_skip_external_secret_sources()
  （读 bool 标志），已抽为 core/recovery_state.py，_early_recovery 改调 core 的 setter/getter，
  env_loader 迁入 core。

每批迁移后重跑测试并修正 mock patch 目标（sparkii_cli.<mod>.X → core.<mod>.X）。
当前 import sparkii_cli 133 → 76；import gateway 仍 11。core/ 现有 33 个模块。
剩余 76 主要是 auth/plugins/providers/lifecycle/middleware/profiles/loops 等中等/大簇，
以及 S5 边缘能力、S6 产品层的反向依赖（后两者属下沉/移出，不是迁 core）。


### Phase A 续（providers + 版本/插件状态，2026-08-20）

- providers 包（provider ABC + 注册 + 入口点发现）已清掉两条 sparkii_cli 懒依赖：
  __version__ 迁到 core/version.py（sparkii_cli/__init__.py re-export），插件启停状态
  读法抽为 core/plugin_state.py（get_enabled_plugins/get_disabled_plugins），
  plugins.py 与 providers 都改从 core 读取。
- import sparkii_cli 133 -> 74（累计）；import gateway 仍 11；core/ 约 36 个模块。
- 相关测试通过；仅剩既有的 Windows 符号链接权限、GBK 编码、legacy-dict 迁移等环境性失败。
