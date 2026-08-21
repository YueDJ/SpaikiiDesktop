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

**Step 2b 完成**（2026-08-20 晚间更新）：
- `cron/scheduler.py` 的 20 处 gateway 引用全部消除：
  - 纯函数下沉：`gateway/response_filters.py` → `core/response_filters.py`
    （cron 与 webhook 共享同一个沉默匹配器，gateway 侧改为转发 shim）；
  - 新增注入桥 `core/cron_delivery.py`（Platform/PlatformConfig/SessionSource/
    BasePlatformAdapter/DeliveryRouter/mirror_to_session/resolve_delivery_transport/
    relay_fronted_platforms/apply_media_policy_env/media 助手/沉默匹配器），
    `gateway/cron_delivery.py` 在 `gateway/__init__` 时注册（懒加载避免环）；
  - 配置读取改 `core.config.get_gateway_config()`（沿用 Step 1 的 reader）；
    平台注册表改 `core.plugins.get_platform_registry()`。
- 测试：tests/cron 的 `gateway.config.load_gateway_config` 桩点按约定改
  `core.config.get_gateway_config`；98 通过，剩余失败均为既有
  （fork Platform 枚举缺消息平台成员且值为 None、Windows 路径双反斜杠）。
- **验证数字**：phase0 保持 **0**；block4 **6 → 5**（cron/scheduler.py 出列，
  仅剩 5 个 dev 脚本豁免）。core repo 对前端的运行时依赖彻底清零。
- **下一步**：Step 3 前端 repo 脚手架（pyproject/package.json 拆分 + 物理迁移）。

**Step 3 完成**（2026-08-21 更新）：
- 前端独立 repo 落地：`C:\Users\YDJ\Desktop\sparkiidesktop-frontends`
  （git init，初始提交，README 记录来源 commit `003d48497e`）。
- 迁出内容（git archive 抽取跟踪文件）：cli.py、gateway/、sparkii_cli/、
  tui_gateway/、acp_adapter/、ui-tui/、apps/、website/、tests-js/ +
  6 个前端测试目录（gateway/sparkii_cli/tui_gateway/acp/acp_adapter/cli）+
  5 个 gateway 依赖的 dev 脚本（scripts/observability 等）。
- 前端仓库脚手架：`pyproject.toml`（包名 sparkii-frontends，依赖
  `sparkii-agent` 裸名 + prompt_toolkit/fastapi/uvicorn/starlette/aiohttp 等
  前端专属依赖；console scripts sparkii/sparkii-acp）、package.json
  （workspaces: apps/*, ui-tui, ui-tui/packages/*, tests-js）、.gitignore、
  README。
- core 仓库瘦身：git rm 迁出目录（4922 文件）；pyproject 移除
  gateway/sparkii_cli/tui_gateway/acp_adapter 包与 cli py-module、sparkii/
  sparkii-acp 入口、gateway 资产；packages.find 补 core/core.*；
  package.json 精简；sparkii_bootstrap 说明更新。
- 依赖接线（dev）：先 `pip install -e <core>` 再 `pip install -e <frontends>`
  （setup.py 有 Nix 外 wheel 构建守卫，故不用 file:// wheel 依赖）；
  发布期换 git 依赖。验证：两仓 ast.parse 全过；跨仓导入
  （cli/gateway/sparkii_cli/tui_gateway/acp_adapter + core.*）OK；
  `sparkii --help` 全命令面正常；`sparkii-agent --help` 正常；
  core phase0 仍为 0。
- 已知中间态：core repo 的 tests/agent|tools|cron|plugins|e2e 等仍有引用
  前端包的测试文件（Step 4 按扫描 CSV 逐文件迁移），拆分前这两类测试暂红。
- **下一步**：Step 4 物理/测试迁移收尾（tests 逐文件判定 + 两仓 CI 拆分），
  Step 5 依赖审计与发布接线，Step 6 Dockerfile/nix/文档更新。

**Step 4 完成**（2026-08-21 更新）：
- 前端仓库远端就位并推送：`github.com/YueDJ/SparkiiDesktop-Frontends`
  （初始提交 46df06d → origin/main）。
- 测试逐文件迁移：core 中 186 个引用前端包的测试文件迁至前端仓库
  （含根 tests/conftest.py、__init__.py、run_interrupt_test.py 及 6 个子目录
  conftest 复制；2 个被前端测试依赖的 agent helper 复制到前端）。core
  剩余 tests 收集无任何前端包 ModuleNotFoundError；前端仓库收集 13999 个
  测试，剩余 55 个收集错误全部为既有环境缺口（acp/mcp 包未装、
  plugins.platforms/nous 死引用、e2e conftest 已在 HEAD 删除、AppData 权限）。
- CI 拆分：core 删除 8 个前端专属 workflow（deploy-site/docs-site-checks/
  e2e-desktop/infographic-check/js-tests/js-autofix/skills-index×2），
  osv-scanner 移除 website lockfile 行；前端仓库新增 tests.yml（checkout
  core + 双 editable 安装 + 前端测试）与 js-tests.yml（npm workspaces），
  其余 8 个随迁 workflow 待 Step 5/6 适配（跨仓 checkout skills/website）。
- **下一步**：Step 5 依赖审计与发布接线（frontends 依赖改 git URL、
  CI 跨仓 checkout 正式化）、Step 6 Dockerfile/nix/文档更新。

**Core 仓库清理**（2026-08-21 更新）：
- 删除前端/产品残留：logo-concepts、mcp-research-data、datagen-config-examples、
  .qoder（729 文件 repowiki 生成物）、.plans（产品计划）、sparkii 启动器、
  package-lock.json、cli-config.yaml.example、setup-sparkii.sh、
  REBRAND_REPORT.md、sparkii-already-has-routines.md、.bytecode-fingerprint、
  多语言产品 README、sparkii_agent.egg-info（可再生成）。
- 一次性迁移脚本移除（git 历史保留）：phase0_m1/s1/s2a/s2b/s3d/auth_closure/
  block4_repair|rewrite|sink|test_rewrite；保留两个可复跑扫描器
  （phase0_import_scan.py、phase0_block4_scan.py）。
- 前端 dev 工具脚本与文档移除：discord-voice-doctor、iso-certify、
  docker_rebootstrap_nous_session、ci/classify_changes、billing/relay/profile-
  routing/streaming-tts/telegram-plan/kanban-dialogs/multi-gateway 等。
- 文档重写：README.md、AGENTS.md 改为 core 内核聚焦版（frontend 指向
  sparkii-frontends）；CONTRIBUTING.md 结构章节与 SECURITY.md 表面清单修剪。
- JS 工具链（eslint/npmrc/nvmrc/prettier/cli-config 示例）复制到前端仓库。
- 保留待 Step 6 处理：Dockerfile/docker-compose/docker/nix/flake/.envrc
  （产品部署，需双仓适配）。保留被 core 引用的 locales/assets/evals/
  optional-mcps/native/contributors。
- 验证：core 导入正常；phase0/block4 扫描仍为 0。

**Step 5/6（部分完成）**（2026-08-21 更新）：
- 依赖审计：前端 pyproject 按"惰性依赖拆 extras"重构 —— base 只留
  import 期必需（prompt_toolkit/fastapi/uvicorn/starlette/python-multipart/
  pywin32），socks/bedrock/discord/qrcode/mutagen/setproctitle/playwright/
  daytona/aiohttp 拆入 extras（与 core 的 lazy-install 哲学一致）。
- 发布接线：core setup.py 新增 `SPARKII_ALLOW_PYPI_BUILD=1` 逃生门
  （前端以 git URL 依赖时 pip 需构建 core wheel；默认仍禁止）；
  前端 pyproject 注明发布期把 `sparkii-agent` 换成 git URL。
- CI：前端 tests.yml/js-tests.yml 可用；docs-site-checks.yml 重写为跨仓
  checkout（core → ../sparkii-core，`SPARKII_CORE_SKILLS_ROOT`），
  extract/generate 脚本已支持该 env；retry/get-app-token action 复制到位；
  6 个随迁部署 workflow（deploy-site/e2e-desktop/infographic-check/
  js-autofix/skills-index×2）挂起（*.yml.disabled），待重建；
  npm workspaces 结构校验通过。core 侧删 npm lockfile-diff workflow、
  osv-scanner 清理、whatsapp-bridge 迁前端。
- Step 6 部分：产品 Docker 部署（Dockerfile/docker-compose/docker/
  .dockerignore/.hadolint）迁前端，前端新增两仓基线 Dockerfile
  （core 从 git 安装，SPARKII_ALLOW_PYPI_BUILD=1）；bug/setup 支持模板迁前端。

**Step 6 完成 — nix/Docker 双仓验证**（2026-08-21，WSL 实机验证）：
- **core 侧 nix 裁剪为内核**：flake 只保留 nixpkgs/flake-parts/pyproject-nix/
  uv2nix/pyproject-build-systems 输入；`sparkii-agent.nix` 只构建
  `sparkii-agent` 内核二进制（wrapper 含 bundled skills/plugins/locales/mcps），
  passthru 暴露 `sparkiiVenv/runtimeDeps/pythonPath`；`packages.nix` 删
  tui/web/desktop/messaging/update-npm-lockfile 变体；devShell 只留
  Python venv + uv + sandbox；checks 重写为内核检查（cross-eval/
  build-package/bundled-*/extra-*）。删除 lib/tui/web/desktop/module
  文件及 npm 锁文件（迁移到前端仓库）。
- **前端 nix 落地**（`sparkiidesktop-frontends/flake.nix`）：以 core 为
  flake input（开发期 `git+file:`，发布期换 `github:YueDJ/SparkiiDesktop`）；
  新增 `nix/frontends-python.nix`（前端 Python 层 pip --no-deps 叠加到
  core venv，PYTHONPATH 合并，无需前端 uv.lock）；lib/tui/desktop 恢复
  到前端仓库（`web` 包删除——`web/` 目录早已移除，web.nix 是死代码）；
  NixOS/Home-Manager 模块、configMergeScript、产品 checks（20 项：
  cli-commands/service-argv/config-roundtrip/bundled-tui/managed-guard/
  module parity 等）随产品迁前端；devShell 叠加 npm workspace + E2E
  Wayland 工具。
- **验证结果（WSL Ubuntu 26.04 + Determinate Nix + Docker）**：
  - core `nix flake show` 通过；前端 `nix flake show` 通过
    （packages: default/minimal/desktop/sparkiiTui/node-gyp/
    update-npm-lockfile；checks ×20；modules/overlays/devShells）。
  - 前端 `nix build .#default` 干跑通过（sparkii-0.20.0 + frontends-
    python + sparkii-tui + core venv 全部 derivation 正确）。
  - ⚠️ 完整 `nix build` 因本机网络环境受限未能在本会话跑通：
    cache.nixos.org 对该 nixpkgs 提交（0954f7e，2026-07-29）覆盖不全，
    ftpmirror.gnu.org 等源码镜像被网络代理间歇 502/TLS 中断，bash 补丁
    及 bootstrap 源码下载反复失败（已预取补丁越过 bash，后续仍卡在
    acl/sed 等 fetchurl）。属环境问题，与配置无关；在缓存完整或镜像
    可达的机器上可正常构建。
  - Docker 镜像构建成功 + 容器冒烟通过（`sparkii --help` 全命令面、
    `sparkii version`、cli/gateway/sparkii_cli/tui_gateway/acp_adapter/
    core 全导入 OK）。
- **顺带修掉的两个真实 bug**：`.dockerignore` 的 `*.md` 规则把 README.md
  过滤出构建上下文（Dockerfile 又要 COPY 它 → 构建失败）；core 阶段的
  python:3.12-slim 没装 git，pip 无法从 git 安装 core（已补 apt git）。
- **遗留项已清**（2026-08-21）：前端 flake 的 core 输入已改为
  `github:YueDJ/SparkiiDesktop` 并提交 `flake.lock`（锁定 core
  `8239fb7d1b`；锁定后 `nix flake show` 与构建干跑复验通过）。
  本地开发用 `--override-input core git+file://<path>` 覆盖，README
  已记录用法。前端 messaging extras（discord/telegram/slack 等）依赖
  由 core venv 的 `all` 组直接覆盖（core uv.lock 已验证），nix 侧无需
  二次安装。

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
