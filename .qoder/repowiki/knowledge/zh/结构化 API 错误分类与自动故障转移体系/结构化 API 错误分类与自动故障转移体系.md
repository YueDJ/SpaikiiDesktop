---
kind: error_handling
name: 结构化 API 错误分类与自动故障转移体系
category: error_handling
scope:
    - '**'
source_files:
    - agent/error_classifier.py
    - agent/errors.py
    - run_agent.py
    - agent/conversation_loop.py
    - agent/chat_completion_helpers.py
    - agent/context_compressor.py
    - agent/agent_runtime_helpers.py
    - sparkii_logging.py
    - agent/transports/base.py
    - tests/run_agent/test_18028_content_policy_blocked.py
    - tests/run_agent/test_31273_402_not_retried.py
    - tests/run_agent/test_auth_provider_failover.py
---

## 1. 整体方案

该仓库采用「集中式错误分类 + 重试/故障转移循环」的架构来处理 LLM/外部 API 调用失败。核心思路是：所有上游 SDK（OpenAI、Anthropic、Bedrock、Gemini、xAI、OpenRouter 等）抛出的异常，统一被 `agent/error_classifier.py` 中的 `classify_api_error()` 解析为结构化的 `ClassifiedError`，其中包含枚举化的 `FailoverReason`（如 `auth`、`billing`、`rate_limit`、`context_overflow`、`timeout`、`server_error`、`model_not_found`、`content_policy_blocked` 等），以及 `retryable`、`should_compress`、`should_rotate_credential`、`should_fallback` 等恢复动作提示。上层 `run_agent.py`、`conversation_loop.py`、`chat_completion_helpers.py`、`context_compressor.py` 等模块根据这些提示执行重试、凭证轮换、上下文压缩、模型/提供商回退或立即中止。

日志系统通过 `sparkii_logging.py` 提供统一的 `setup_logging()`，将 `agent.log`（全量）、`errors.log`（WARNING+）、`gateway.log`、`gui.log` 按组件分离输出，并使用 `RedactingFormatter` 脱敏敏感信息；Windows 下使用 `concurrent_log_handler` 避免多进程旋转日志时的 `PermissionError`。日志中嵌入会话 ID（`set_session_context`）以便关联排查。

## 2. 关键文件与包

- **错误分类核心**：`agent/error_classifier.py` — 定义 `FailoverReason` 枚举、`ClassifiedError` dataclass、HTTP 状态码分类器 `_classify_by_status`、400/402 细分器 `_classify_400` / `_classify_402`、消息模式匹配器 `_classify_by_message`、错误代码提取器 `_extract_error_code`、OpenRouter 上游错误检测 `_is_openrouter_upstream_error` 等。
- **领域专用异常**：`agent/errors.py` — 仅定义三个细粒度异常：`SSLConfigurationError`、`EmptyStreamError`、`MoAPresetNotFoundError`（后者被分类器显式识别并映射为 `model_not_found`）。
- **各子系统自定义异常**（分散在各模块，未统一基类）：
  - `agent/gemini_native_adapter.py::GeminiAPIError`
  - `agent/lsp/protocol.py::LSPProtocolError` / `LSPRequestError`
  - `agent/pet/*` 下的 `GenerationError` / `ManifestError` / `PetStoreError`
  - `agent/plugin_llm.py::PluginLlmTrustError(PermissionError)`
  - `agent/secret_scope.py::UnscopedSecretError`
  - `agent/subagent_lifecycle.py::SubagentLifecycleError`
  - `agent/trace_upload.py::TraceRedactionError`
  - `agent/transports/codex_app_server.py::CodexAppServerError`
  - `cron/blueprint_catalog.py::BlueprintFillError`、`cron/scheduler.py::CronSchedulerRegistrationError`
  - `gateway/platforms/api_server.py::_ProviderAuthResolutionError` 等
  - `gateway/platforms/qqbot/chunked_upload.py::UploadDailyLimitExceededError` / `UploadFileTooLargeError`
  - `gateway/platforms/signal_rate_limit.py::SignalRateLimitError` / `SignalSchedulerError`
  - `gateway/turn_lease.py::TurnLeaseTimeoutError(TimeoutError)`
- **消费方**：`run_agent.py`、`agent/conversation_loop.py`、`agent/chat_completion_helpers.py`、`agent/context_compressor.py`、`agent/agent_runtime_helpers.py` 均导入 `FailoverReason` 和/或 `classify_api_error`。
- **测试覆盖**：`tests/run_agent/test_*` 大量用例直接断言 `classify_api_error` 的分类结果（如 `test_18028_content_policy_blocked.py`、`test_31273_402_not_retried.py`、`test_auth_provider_failover.py`、`test_thinking_timeout_guidance.py`）。

## 3. 架构与约定

### 3.1 分类流水线优先级
`classify_api_error()` 严格按以下顺序处理异常（见源码注释与分支顺序）：
1. **提供商特定模式**（最高优先级）：如 Anthropic thinking block 签名错误、long-context tier gate、OAuth beta 禁用、llama.cpp grammar pattern 拒绝、xAI Grok 订阅耗尽。
2. **HTTP 状态码分类**：401→auth（带 credential rotation）、403→billing/auth（按关键词区分）、402→billing vs rate_limit 歧义消除、404→model_not_found vs provider_policy_blocked vs unknown、408→timeout、413→payload_too_large（触发压缩）、429→overloaded vs upstream_rate_limit vs per-credential rate_limit、500/502→format_error（含 request validation 信号时）vs context_overflow vs server_error、503/529→overloaded。
3. **结构化错误码分类**：`resource_exhausted`/`throttled`→rate_limit；`insufficient_quota`/`payment_required`/`balance_depleted` 等→billing；`context_length_exceeded`→context_overflow。
4. **消息文本模式匹配**：当无 status code 时，对 `str(error)`、`body.message`、`metadata.raw` 拼接后的字符串进行子串匹配，覆盖 billing/rate_limit/overloaded/context_overflow/auth/model_not_found/timeout 等场景。
5. **SSL/TLS 分支**：证书验证失败（确定性错误，不重试）→ `ssl_cert_verification`；TLS 中间握手告警（瞬态）→ `timeout`。
6. **服务端断开 + 大会话** → 推断为 context overflow 并触发压缩；推理模型长思考流断开则降级为 timeout。
7. **传输层启发式**：`ReadTimeout`/`ConnectTimeout`/`SSLError`/`ConnectionError`/`OSError` 等类型名命中 → `timeout`。
8. **兜底**：`unknown`（可重试，指数退避）。

### 3.2 恢复动作语义
每个 `ClassifiedError` 携带四个布尔提示：
- `retryable`：是否进入重试循环（auth/billing/format_error/content_policy_blocked 通常 False）。
- `should_compress`：是否先做上下文压缩再重试（context_overflow/payload_too_large/image_too_large）。
- `should_rotate_credential`：是否轮换凭证池（rate_limit/auth/billing）。
- `should_fallback`：是否切换到备用 model/provider（auth、billing、model_not_found、provider_policy_blocked、upstream_rate_limit）。

### 3.3 异常设计原则
- 业务域异常集中在各自模块内定义，继承 Python 内置异常（`RuntimeError`、`ValueError`、`Exception`、`TimeoutError`、`PermissionError`），**没有统一的业务异常基类**。分类器通过 `isinstance(error, MoAPresetNotFoundError)` 等精确类型检查来捕获特定异常。
- 对外部 SDK 异常不做包装，而是由分类器在运行时抽取 `.status_code`、`.body`、`.response.json()`、`__cause__`/`__context__` 链上的字段，以兼容 OpenAI、litellm、Bedrock、OpenRouter 等多种异常形状。
- 对于“确定性失败”（SSL 证书验证失败、内容策略拦截、格式错误、模型不存在）一律设置 `retryable=False`，避免浪费重试预算和用户配额。

### 3.4 日志与可观测性
- 所有日志通过 `sparkii_logging.setup_logging()` 初始化，统一写入 `~/.sparkii/logs/` 下的分文件。
- `errors.log` 仅记录 WARNING+，便于快速定位问题。
- 日志格式注入 `[session_id]` 标签，支持跨进程追踪同一会话。
- 使用 `RedactingFormatter` 防止密钥泄露到磁盘。

## 4. 约定与约束

- **禁止绕过分类器**：所有 API 调用失败必须经 `classify_api_error()` 分类后再决定重试/回退策略，不得自行判断 HTTP 状态码后直接重试或中止（分类器注释明确说明其替代了“散落的 inline string-matching”）。
- **新增错误类型应优先扩展 `FailoverReason` 枚举**，而非引入新的顶层异常类型；只有真正需要跨模块传播的业务错误才定义新异常类。
- **模式列表维护规范**：新增 provider 错误文案需加入对应 `_*_PATTERNS` 常量（如 `_BILLING_PATTERNS`、`_RATE_LIMIT_PATTERNS`、`_CONTEXT_OVERFLOW_PATTERNS` 等），并保持足够窄以避免误匹配（例如 `_CONTENT_POLICY_BLOCKED_PATTERNS` 刻意使用 `content_filter` 下划线形式而非通用词 `content filter`）。
- **4xx/5xx 默认行为**：4xx 默认视为 `format_error`（不可重试），5xx 默认视为 `server_error`（可重试），但 400/402/403/404/408/413/429/500/502/503/529 均有专门分支覆盖。
- **SSL 证书验证失败不重试**：这是明确的硬性规则（注释引用 Claude Code v2.1.199 的设计），因为每次重试都会产生相同的握手失败，应立即向用户展示修复指引。
- **OpenRouter 上游限流不轮换凭证**：检测到 `metadata.provider_name` 或 `metadata.raw` 时标记为 `upstream_rate_limit`，仅回退到不同 model，不消耗用户 key 的配额。
- **测试要求**：新增分类逻辑需在 `tests/run_agent/` 中添加对应断言，确保分类结果稳定（仓库已有大量针对具体 issue 编号的回归测试）。