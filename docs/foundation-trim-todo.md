# Foundation Trim — 剩余待办（Provider 瘦身长尾）

## 已完成（不要重做）

- 静态 PROVIDER_REGISTRY 已缩到 2 个：anthropic、openai-api（core/provider_registry.py）。
- plugins/model-providers/ 已删 34 个 provider 插件目录，保留 anthropic + custom。
- arcee 已完整删除（代码 + 测试）。
- 已删 105 个 provider 专属测试文件。
- models.py 已删 18 块死代码（部分，可能还有残留）。

## 剩余三块（按顺序推进）

### Block A — 烘焙死代码清理
把被删 provider 的条目从以下文件移除（引用的 provider 已不存在，是死数据）：
- sparkii_cli/providers.py — SparkiiOverlay 条目 + 别名映射
- core/config_defaults.py — 各 *_API_KEY / *_BASE_URL 配置块
- sparkii_cli/doctor.py — 诊断元组 + 显示名映射
- sparkii_cli/model_normalize.py — 模型别名/归一化映射
- sparkii_cli/model_switch.py — ModelIdentity 映射
- agent/model_metadata.py — host→provider 映射
- sparkii_cli/auth.py — provider 别名
- core/model_resolution.py — provider 别名
- sparkii_cli/main.py — provider 列表项
- sparkii_cli/setup.py — provider 模型列表
- sparkii_cli/models.py — 上轮未删干净的 _PROVIDER_MODELS / ProviderEntry 残留

方法：AST 定位 Dict 的字符串 key / List 里 Call 的首个字符串参数，匹配被删 provider 名后按
key.lineno → value.end_lineno 删除（FunctionDef/ClassDef.lineno 不含装饰器，别用错）。

### Block B — OAuth 流程 + Nous 产品
- sparkii_cli/auth.py：删 nous / openai-codex / xai-oauth / qwen-oauth / minimax-oauth / copilot-acp
  的登录/刷新函数（设备码、token 交换、refresh、OAuth 分支）。
- Nous 一整套：sparkii_cli/nous_account.py、nous_subscription.py、nous_billing.py、nous_auth_keepalive.py
  等，以及 agent/ 里 nous 相关（nous_rate_guard、credits 等）。
- 删后清理 core/provider_registry.py 里无引用的 OAuth 常量（DEFAULT_NOUS_*、MINIMAX_OAUTH_*、
  DEFAULT_CODEX_BASE_URL、DEFAULT_XAI_OAUTH_BASE_URL、DEFAULT_QWEN_BASE_URL、DEFAULT_COPILOT_ACP_BASE_URL 等）。

### Block C — 共享测试文件里的 provider 断言
跑 pytest tests/sparkii_cli/test_api_key_providers.py tests/sparkii_cli/test_models.py 定位失败
测试类/方法，逐类删被删 provider 的专属断言，保留通用断言。

## 节奏
删一块 → 跑相关测试 → 红数下降 → 下一块。不要一次性全删。

## 验证命令
.venv\Scripts\python.exe -m pytest <paths> -q -p no:cacheprovider --basetemp=.pytest-tmp
.venv\Scripts\python.exe scripts\phase0_import_scan.py

## 已知既有失败（不是本次引入，不要修）
- 中文 Windows GBK 编码读 UTF-8（UnicodeDecodeError: gbk codec ...）
- Windows 路径差异（~/.sparkii vs AppData/Local/sparkii）
- test_auth_remove_codex_migrates_legacy_dict_suppression（legacy dict 迁移逻辑缺失）
- test_rejects_symlink_escape（Windows 符号链接权限 WinError 1314）

## 已知坑
- Python 3.12 ast 的 FunctionDef/ClassDef.lineno 不含装饰器，抽取时 @dataclass/@contextmanager 会漏。
- 模块迁到 core 后，测试里的 patch("sparkii_cli.<mod>.X") / patch.object(...) 要改成 core.<mod>.X。
- 迁移脚本的 shutil.move 要加 not dst.exists() 守卫，避免重跑时用 shim 覆盖真实文件。
- Windows 上偶发 Errno 22（瞬时文件锁），写文件加重试。
- --basetemp=.pytest-tmp 规避沙箱对 %TEMP% 的写权限限制。
