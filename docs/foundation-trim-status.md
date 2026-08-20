# Sparkii 底座裁剪 — 状态文档（2026-08-20）

## 基线（固化数字）

| 指标 | 值 |
|---|---|
| import sparkii_cli 反向依赖 | **68**（起始 133） |
| import gateway 反向依赖 | **11** |
| 核心反向 import 文件数 | **72**（扫描 389 个核心文件） |
| core/ 模块数 | 39 |
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

## 剩余四块

### Block 1 — S5 实现下沉（低价值，可选）
把 tools/browser_tool.py、image_generation_tool.py、video_generation_tool.py、tts_tool.py
的实现迁到对应 plugins/。运行时收益低（工具已门控），主要为了物理归位。
建议：跳过或最后做。

### Block 2 — S6 产品层移出
可干净移除：agent/account_usage.py、curator.py、outbound_webhooks.py、pet/（仅被 cli/gateway/tui 表面引用）。
纠缠（需依赖反转）：agent/display.py（被 model_tools/conversation_loop/tool_executor 引用）、
billing_links.py（被 conversation_loop 引用）、background_review.py（被 run_agent 引用）、
monitoring/gateway_health*（监控子系统）。

### Block 3 — auth/plugins 收尾（迁 core）
auth 凭据解析（OAuth 已删，只剩通用 api-key 解析）迁 core；plugins 加载器迁 core（需先解与 gateway 的耦合）。

### Block 4 — S7 前端独立
cli.py、gateway、ui-tui、apps、website、acp_adapter 迁到独立 repo，消费 core 作为库。

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
