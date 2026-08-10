---
kind: logging_system
name: Hermes/Sparkii 集中式日志系统：多文件轮转、组件路由与敏感信息脱敏
category: logging_system
scope:
    - '**'
source_files:
    - sparkii_logging.py
    - agent/redact.py
    - sparkii_cli/logs.py
    - acp_adapter/entry.py
    - gateway/run.py
    - sparkii_cli/main.py
    - agent/agent_init.py
---

## 1. 使用的系统与框架

项目使用 Python 标准库 `logging` 作为唯一日志框架，并通过自研的 `sparkii_logging.py` 模块进行统一初始化。核心依赖包括：
- `logging.handlers.QueueHandler` + `QueueListener`：将文件写入异步化，避免事件循环阻塞。
- `concurrent_log_handler.ConcurrentRotatingFileHandler`（仅 Windows）：解决多进程同时写入同一 `agent.log` 时的 `PermissionError [WinError 32]` 问题；POSIX 上仍使用 stdlib `RotatingFileHandler`。
- `agent.redact.RedactingFormatter`：基于正则的敏感信息脱敏格式化器，所有落盘日志均经此处理。
- 通过 `logging.setLogRecordFactory` 注入全局 `session_tag` 字段，实现会话级上下文关联。

## 2. 关键文件与包

| 文件 | 职责 |
|---|---|
| `sparkii_logging.py` | 中心化的 `setup_logging()` 入口，定义日志文件布局、级别、轮转策略、组件路由、异步队列、会话上下文注入 |
| `agent/redact.py` | 敏感信息脱敏逻辑（API Key、JWT、DB 连接串、Authorization 头、URL userinfo 等），提供 `RedactingFormatter` |
| `sparkii_cli/logs.py` | `sparkii logs` CLI 子命令，支持按文件/级别/会话/组件/时间范围过滤和实时 follow |
| `acp_adapter/entry.py` | ACP 适配器独立入口，单独配置 stderr 输出并静默探针方法的噪声日志 |
| `gateway/run.py`、`sparkii_cli/main.py`、`agent/agent_init.py` | 调用 `setup_logging(mode=...)` 启动各进程时装配日志 |

## 3. 架构与设计决策

### 3.1 日志文件布局
所有日志位于 `~/.sparkii/logs/`（profile-aware，由 `get_sparkii_home()` 解析）：
- `agent.log`（默认 INFO+，5MB 轮转 × 3 份）：主活动日志，捕获全部 agent/tool/session 行为。
- `errors.log`（WARNING+，2MB × 2）：快速排障专用，只写警告与错误。
- `gateway.log`（INFO+，5MB × 3）：仅接收 `gateway.*`、`sparkii_plugins`、`plugins.platforms` 命名空间的记录。
- `gui.log`（INFO+，10MB × 5）：仅接收 `sparkii_cli.web_server`、`sparkii_cli.pty_bridge`、`tui_gateway.*`、`uvicorn.*` 的记录。
- `desktop.log`、`mcp-stderr.log`：桌面应用与 MCP 子进程 stderr 重定向输出（由 `sparkii_cli/logs.py` 识别）。

### 3.2 组件路由机制
通过 `_ComponentFilter` 匹配 logger name 前缀，配合 `COMPONENT_PREFIXES` 字典将不同子系统路由到对应文件：
```python
COMPONENT_PREFIXES = {
    "gateway": ("gateway", "sparkii_plugins", "plugins.platforms"),
    "agent": ("agent", "run_agent", "model_tools", "batch_runner"),
    "tools": ("tools",),
    "cli": ("sparkii_cli", "cli"),
    "cron": ("cron",),
    "gui": ("sparkii_cli.web_server", "sparkii_cli.pty_bridge", "tui_gateway", "uvicorn"),
}
```
该映射同时被 `sparkii logs --component <name>` 复用。

### 3.3 会话上下文注入
通过替换全局 `logging.getLogRecordFactory()`，在每个 `LogRecord` 创建时注入 `session_tag`（形如 ` [sess_abc]`）。调用方在对话开始时调用 `set_session_context(session_id)`，结束时调用 `clear_session_context()`。该机制对进程内所有 logger（含第三方 handler）生效，避免了 `logging.Filter` 可能遗漏的传播路径。

### 3.4 异步文件写入
所有 RotatingFileHandler 都经由共享的 `queue.SimpleQueue` + `QueueListener` 投递到后台线程执行，避免跨进程旋转锁阻塞 asyncio 事件循环。`flush_log_queue()` 用于测试同步等待；`drain_log_queue(timeout=1.0)` 用于硬退出路径下的有界等待，防止旋转锁死锁拖垮进程退出。

### 3.5 安全默认值
- 所有日志格式使用 `RedactingFormatter`，禁止明文密钥落盘。
- 第三方噪音日志（`openai`、`httpx`、`httpcore`、`asyncio`、`grpc`、`urllib3`、`websockets` 等）默认降级为 WARNING。
- 脱敏开关 `_REDACT_ENABLED` 默认 `true`，可通过 `security.redact_secrets: false` 或 `SPARKII_REDACT_SECRETS=false` 关闭，但会在启动时记录告警。

### 3.6 平台差异处理
- Windows：用 `concurrent-log-handler` 替代 stdlib `RotatingFileHandler`，并通过 `handleError` 静默其锁超时异常，避免 slash-worker 把 traceback 回显到聊天输出。
- NixOS managed mode：自定义 `_ManagedRotatingFileHandler` 在 `_open()` 和 `doRollover()` 后强制 `chmod 0o660`，确保 setgid 组可共享日志；同时检测外部 rotation（logrotate、unlink）并自动重建 fd。

## 4. 约定与约束

- **单点初始化**：所有进程必须通过 `sparkii_logging.setup_logging(mode=...)` 启动日志，禁止各自 `basicConfig`。ACP 适配器是例外，它直接配置 stderr 以保留 stdout 给 ACP JSON-RPC 传输。
- **模式驱动路由**：`mode="gateway"` 生成 `gateway.log`，`mode="gui"` 生成 `gui.log`，其他模式不产生这些文件。
- **日志级别来源优先级**：参数 `log_level` > `config.yaml logging.level` > 默认 `INFO`。
- **轮转大小/备份数**：参数 `max_size_mb` / `backup_count` > `config.yaml logging.max_size_mb` / `logging.backup_count` > 默认 5MB/3 份。
- **会话标签**：每个对话开始必须调用 `set_session_context`，否则日志行无 `[session_id]` 标记，影响过滤。
- **敏感信息不可绕过**：`redact_sensitive_text(force=True)` 路径（如 CDP URL 脱敏）不受 `SPARKII_REDACT_SECRETS=false` 影响。
- **Windows 并发写入**：多进程同时写 `agent.log` 是预期场景（TUI、gateway、hy_memory、MCP server 等），必须依赖 `concurrent-log-handler` 的跨进程锁；任何绕过该机制的直接 `open("agent.log", "a")` 都会导致 WinError 32。
- **CLI 查询一致性**：`sparkii logs --component` 使用的组件前缀表与 `sparkii_logging.COMPONENT_PREFIXES` 完全一致，新增组件需同步更新两处。
- **日志格式**：默认格式 `%(asctime)s %(levelname)s%(session_tag)s %(name)s: %(message)s`；verbose 模式使用 `%(asctime)s - %(name)s - %(levelname)s%(session_tag)s - %(message)s`，时间格式 `%H:%M:%S`。
- **stderr 编码**：通过 `_safe_stderr()` 包装 `sys.stderr`，遇到非 UTF-8 控制台编码时用 `errors='replace'` 降级，保证日志永不因编码崩溃丢失。