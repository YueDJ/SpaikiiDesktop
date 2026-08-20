# Sparkii 底座裁剪 — 状态文档（2026-08-20）

## 基线（固化数字）

| 指标 | 值 |
|---|---|
| import sparkii_cli 反向依赖 | **43**（起始 133；Block 3 后 61→43） |
| import gateway 反向依赖 | **9** |
| 核心反向 import 文件数 | **50**（扫描 376 个核心文件） |
| core/ 模块数 | 41 |
| 静态 provider 数 | 2（anthropic + openai-api） |
| 核心工具集 | 17 |

## 已完成

- 依赖分层方法（S0-S7）+ 可复跑 import 扫描器 scripts/phase0_import_scan.py。
- 核心抽取：session_context、config 组、auth 三簇（auth_store/credential_sources/provider_registry）、
  normalize_provider、叶子服务（env_loader/_subprocess_compat/urllib_security/timeouts/...）、
  providers 包、version、plugin_state。
- Provider 瘦身：36→2 provider；删 34 插件、105 测试文件、OAuth 流程、Nous 产品、烘焙死代码。
- Phase B 第一步：核心工具集 50→17，边缘工具改为 toolset+check_fn 门控。
- 17 个迁移脚本保留在 scripts/phase0*.py，可复跑。
- Block 2（S6 产品层移出）完成：
  - 干净移除并迁至 sparkii_cli：agent/account_usage.py、agent/outbound_webhooks.py、
    agent/curator.py（引擎并入 sparkii_cli/curator.py）、agent/pet/（→ sparkii_cli/pet/）。
  - 依赖反转（不硬删）：
    - billing_links → sparkii_cli/billing_links.py；conversation_loop 改为
      set_billing_block_builder() 注入（cli/gateway/tui 注册）。
    - display → sparkii_cli/display.py（渲染）+ agent/display_provider.py 核心注入钩子
      （spinner/preview/emoji/cute 消息）；安全脱敏归 agent/redact.py、
      工具失败检测归 agent/tool_result_classification.py。
    - background_review → sparkii_cli/background_review.py；run_agent 改为
      set_background_review_provider() 注入，AIAgent 类提示词属性由注册时填充。
    - monitoring：gateway_health/gateway_health_export 不再 import gateway.status，
      改为 set_gateway_status_readers() 注入（gateway/run.py 注册）。

## 剩余四块

### Block 1 — S5 实现下沉（低价值，可选）
把 tools/browser_tool.py、image_generation_tool.py、video_generation_tool.py、tts_tool.py
的实现迁到对应 plugins/。运行时收益低（工具已门控），主要为了物理归位。
建议：跳过或最后做。

### Block 2 — S6 产品层移出
**已完成**（2026-08-20）：
- 干净移除：agent/account_usage.py、curator.py、outbound_webhooks.py、pet/ → sparkii_cli/，
  表面引用（cli.py、gateway/、tui_gateway/、sparkii_cli/、acp_adapter/）已更新。
- 依赖反转：display.py（拆渲染→sparkii_cli/display.py + 核心 provider 钩子）、
  billing_links.py（conversation_loop → 注入 builder）、background_review.py
  （run_agent → 注入 provider）、monitoring/gateway_health*（→ 注入 status readers）。
- 验证：每步 ast.parse → import → pytest（--basetemp=.pytest-tmp）；全量相关测试
  432 passed / 18 failed（全部为已知既有环境失败：GBK 编码、/proc、退役 codex-usage 测试）。

### Block 3 — auth/plugins 收尾（迁 core）
**已完成**（2026-08-20）：
- auth：`sparkii_cli/auth.py` 闭包分析后拆为
  `core/credentials.py`（通用 api-key 凭据解析 + provider-state 持久化 +
  auth 错误映射 + 环境探测）与 `sparkii_cli/auth.py`（CLI-only 交互函数 +
  兼容 re-export shim）。残留 Spotify OAuth 死代码、未引用的 token/refresh
  辅助函数一并删除；copilot/minimax 等不可达分支清理。
  核心消费者改 import `core.credentials` / `core.auth_store` /
  `core.provider_registry` / `core.credential_sources`；测试 patch 目标按约定
  同步改为 `core.*`。
- plugins：`sparkii_cli/plugins.py`（6561 行）先解与 gateway 耦合
  （`gateway.platform_registry` 通过 `set_platform_registry_provider()`
  注入；`PlatformEntry` 数据契约迁 `core/plugin_platform.py`），再整模块迁至
  `core/plugins.py`。8 处 `sparkii_cli.*` 惰性依赖全部改为注入式 bridge
  （platform_actions / profiles / commands / dashboard_auth / main._AUX_TASKS /
  approval_transport / agent_plugins / lifecycle-observer），由各 surface
  模块 import 时注册；`sparkii_cli/plugins.py` 变为纯 `__getattr__` 转发
  shim（patch `core.plugins.X` 对 core 与 shim 消费者同时生效）。
  核心消费者改 import `core.plugins`；lifecycle 观察者通过注入保住
  observability 分发。
- 验证：`phase0_import_scan.py` 中 import sparkii_cli 反向依赖
  **61 → 43**；核心反向 import 文件数 **65 → 50**；全仓 ast.parse 通过；
  相关测试与 HEAD 基线逐批 diff，失败集合完全一致（无新增失败；
  另有 1 个测试由 HEAD 的 ERROR 变为同断言 FAILED，行为等价）。

### Block 4 — S7 前端独立
cli.py、gateway、ui-tui、apps、website、acp_adapter 迁到独立 repo，消费 core 作为库。

**进行中**（2026-08-20 更新）：
- 迁移边界与包结构方案已定稿：`docs/foundation-block4-plan.md`。
- 新增可复跑扫描器 `scripts/phase0_block4_scan.py --csv`（结果落
  `docs/foundation-block4-scan.csv`）。
- **Step 1 完成**（核心侧解耦，两种边界都必须做的部分）：
  - 进程助手下沉 `core/process_utils.py`（_pid_exists / get_process_start_time /
    terminate_pid / is_gateway_supervisor_process + gateway running-pid 注入钩子），
    `gateway/status.py`、`gateway/restart.py` re-export；
  - ACP 编辑审批契约下沉 `core/edit_approval.py`（model_tools 不再 import
    acp_adapter；acp_adapter 保留协议接线 + re-export）；
  - 媒体缓存下沉 `core/media_cache.py`（image/audio/document + 大小上限 +
    GATEWAY_SECRET_CAPTURE_UNSUPPORTED_MESSAGE），`gateway/platforms/base.py`
    re-export；
  - 平台注册表改走 `core.plugins.get_platform_registry()`（新增公开访问器）；
  - gateway 配置读取改走 `core.config.get_gateway_config()` 注入；
  - CLI 配置改走 `core.config.set_cli_config_provider()` 注入（delegate_tool
    不再 import cli）；relay_runtime 改读 `core.config.load_config_readonly()`。
  - 消费方更新：tools/*（async_delegation、browser_tool、local、mcp_tool、
    process_registry、skills_tool）、cron/executions、plugins/google_meet、
    plugins/kanban、plugins/honcho、toolsets、agent/system_prompt、model_tools、
    tools/delegate_tool；测试 patch 目标按约定同步改为 core.*。
- 验证：全仓 3899 个 py 文件 ast.parse 通过；phase0 扫描 **gateway 9→0、
  cli 1→0**（核心反向 import 50→43，剩余 43 均为 sparkii_cli，属 Step 2）；
  block4 扫描 **44→30**（剩余 30 中 27 个在 sparkii_cli/tui_gateway，随迁后
  自然消失；cron/scheduler 1 个 + scripts 2 个 dev 工具留 Step 2/迁移期）。
  相关测试批跑无新增失败（仅剩既有环境失败：Windows PTY/POSIX 路径、
  /proc、signal 平台已退役、acp 包未安装、memo 机制已删）。
- **下一步（Step 2）**：cron/scheduler.py 交付反转 + sparkii_cli 共享服务
  （runtime_provider/models/profiles/tools_config/middleware 等）下沉 core，
  目标 phase0 归零；随后 Step 3 前端 repo 脚手架（见方案文档 §5）。

**Step 2 完成**（2026-08-20 晚间更新）：
- 共享服务下沉 core（21 个模块 + 1 个包）：
  `runtime_provider`、`models`、`model_switch`、`model_catalog`、
  `model_normalize`、`profiles`、`goals`、`heartbeat`、`loops`、
  `kanban_db`、`projects_db`、`inventory`、`tools_config`、`platforms`、
  `middleware`、`lifecycle`、`approval_transport`、`copilot_auth`、
  `managed_uv`、`prompt_size`、`resource_limits`、`kanban_diagnostics`、
  `kanban_specify`、`kanban_decompose`、`profile_describer`、`memory_setup`、
  `observability/`（整包）；`sparkii_cli` 对应文件全部改为转发 shim。
- 新增注入桥：`core/gateway_service.py`（s6/systemd/launchd 服务信息）、
  `core/kanban_bridge.py`（dashboard ws-auth + dispatcher 探针）、
  `core/session_steer.py`（TUI steer authority）、`core.config`
  gateway-config/cli-config reader、`core.process_utils` profile 存活探针。
- 死代码清理：nous_account/nous_subscription/nous 凭据（模块早已删除，
  残余 try/except 引用一并移除）、`import sparkii_cli as` 版本引用改 core.version。
- 边界缺口修复：approval-transport provider 注册（Block 3 遗留）、
  dashboard_auth 基础契约下沉 `core/dashboard_auth.py`（插件可直接继承）。
- 测试：260+ 测试文件 patch/import 目标按约定改 `core.*`；相关测试批跑
  无新增失败（仅剩既有环境失败：acp 包未装、GBK、Windows 路径、退役
  codex/平台、gateway notifier fixture）。
- **验证数字**：phase0 扫描 **43 → 0**（核心反向 import 彻底归零）；
  block4 扫描 **30 → 6**（`cron/scheduler.py` 交付反转 + 5 个 dev 脚本豁免）。
- **剩余里程碑**：`cron/scheduler.py` 的 16+ 处 gateway 交付引用
  （config/session/delivery/mirror/relay/media/response_filters）反转成
  注入钩子（gateway/run.py 注册）——按方案 §2.2 独立推进；随后 Step 3
  前端 repo 脚手架。

## 节奏
删/迁一块 → ast.parse 验证 → import 验证 → 跑相关测试 → 红数下降 → 下一块。

## 验证命令
.venv\\Scripts\\python.exe -m pytest <paths> -q -p no:cacheprovider --basetemp=.pytest-tmp
.venv\\Scripts\\python.exe scripts\\phase0_import_scan.py

## 已知既有失败（不要修）
- 中文 Windows GBK 编码读 UTF-8
- ~/.sparkii 与 AppData/Local/sparkii 路径差异
- test_auth_remove_codex_migrates_legacy_dict_suppression
- test_rejects_symlink_escape（WinError 1314）
- test_sparkii_platforms_share_core_tools / test_sparkii_whatsapp_* / TestResolveToolsetMemo（引用已退役平台/memo 机制）

## 已知坑
- Python 3.12 ast 的 FunctionDef/ClassDef.lineno 不含装饰器。
- 模块迁 core 后，测试 patch("sparkii_cli.X") 要改成 core.X。
- shutil.move 加 not dst.exists() 守卫；写文件加重试（Windows Errno 22 瞬时锁）。
- --basetemp=.pytest-tmp 规避 %TEMP% 权限。
