---
kind: configuration_system
name: Sparkii 配置系统：分层加载、缓存与安全管理
category: configuration_system
scope:
    - '**'
source_files:
    - sparkii_cli/config.py
    - sparkii_cli/config_defaults.py
    - sparkii_cli/env_loader.py
    - gateway/config.py
    - cli-config.yaml.example
---

## 1. 使用的系统与架构

Sparkii 采用 **YAML + .env + 环境变量** 的分层配置模型，核心由 `sparkii_cli/config.py` 实现，默认值集中定义在 `sparkii_cli/config_defaults.py`，`.env` 加载逻辑封装在 `sparkii_cli/env_loader.py`。Gateway 侧通过 `gateway/config.py` 复用 CLI 配置并叠加平台/流式传输等运行时配置。

- **配置文件位置**：`$SPARKII_HOME/config.yaml`（主配置）、`$SPARKII_HOME/.env`（密钥）、`$SPARKII_HOME/.op.env`（1Password 服务账户令牌，gitignore）
- **默认值来源**：`DEFAULT_CONFIG` 字典（含 model、agent、terminal、browser、compression、auxiliary、openrouter、bedrock 等全部字段），`OPTIONAL_ENV_VARS` 描述所有可选环境变量及其元数据（description/prompt/password/category）
- **配置版本迁移**：通过 `_config_version` 字段和 `ENV_VARS_BY_VERSION` 映射追踪新增的 env var，支持从旧 schema 自动迁移
- **受管模式（Managed Mode）**：NixOS/Homebrew 等包管理器安装时通过 `SPARKII_MANAGED` 或 `$SPARKII_HOME/.managed` 标记进入只读模式，禁止直接写 `config.yaml`，改用 `nixos-rebuild switch`

## 2. 关键文件与模块

| 文件 | 职责 |
|---|---|
| `sparkii_cli/config.py` | 配置加载/保存/合并/校验/迁移、路径解析、安全权限设置、进程级缓存、install method 检测 |
| `sparkii_cli/config_defaults.py` | 纯数据模块：`DEFAULT_CONFIG` 与 `OPTIONAL_ENV_VARS`，被 config.py 导入但不可反向依赖 |
| `sparkii_cli/env_loader.py` | `.env` / `.op.env` / managed-scope `.env` 的加载、ASCII 清洗、外部 secret 源（Bitwarden/1Password）注入 |
| `gateway/config.py` | Gateway 平台配置（Telegram/Discord/WhatsApp 等）、会话重置策略、流式传输配置、端口绑定检查 |
| `cli-config.yaml.example` | 用户可复制的完整配置模板 |
| `sparkii_constants` | `get_sparkii_home()`、`get_process_sparkii_home()` 等路径常量（避免循环导入） |
| `utils.atomic_replace` | 原子写入配置文件（先写临时文件再 rename） |

## 3. 架构与设计决策

### 3.1 加载顺序（优先级从高到低）

```text
1. 进程内 os.environ（shell 导出）
2. $SPARKII_HOME/.env（override=True，覆盖 shell 变量）
3. $SPARKII_HOME/.op.env（仅当 OP_SERVICE_ACCOUNT_TOKEN 未设置时，override=False）
4. 项目级 .env（仅在用户 .env 不存在时才生效）
5. managed-scope .env（最后以 override=True 应用，覆盖用户与环境）
6. config.yaml 中的 terminal.* 键重新桥接到 env（确保 YAML 是最终权威）
```

### 3.2 配置合并策略

- `load_config()` 从 `DEFAULT_CONFIG` 开始，深合并用户 `config.yaml`，再合并 profile 覆盖
- 使用 `threading.RLock` 串行化所有读写，因为 libyaml C 扩展对并发 `safe_load` 不安全
- 进程级缓存 `_LOAD_CONFIG_CACHE` 基于 `(path, mtime_ns, size)` 键，避免重复解析；`save_config()` 通过原子写入产生新 inode，下次 load 自动失效
- 原始 YAML 单独缓存 `_RAW_CONFIG_CACHE`，供 `read_raw_config()` 使用

### 3.3 环境变量白名单/黑名单

- **写入黑名单** `_ENV_VAR_NAME_DENYLIST`：禁止通过 dashboard/env writer 写入 `LD_PRELOAD`、`PYTHONPATH`、`PATH`、`EDITOR`、`GIT_SSH_COMMAND`、`SPARKII_HOME`、`SPARKII_PROFILE`、`SPARKII_CONFIG`、`SPARKII_ENV` 等危险变量（仅针对写操作，已存在的值仍可用）
- **已知密钥集合** `_EXTRA_ENV_KEYS` + `OPTIONAL_ENV_VARS.keys()` 构成“Sparkii 已知 env 键”全集，用于 setup 向导、缺失检查、secret source 标注
- **Profile 隔离键** `_PROFILE_MANAGED_ENV_KEYS`：ACP/Copilot 相关键在 profile `.env` 中缺失时被清理，防止父进程泄漏影响路由

### 3.4 安全与权限

- 非容器/非 managed 模式下，`ensure_sparkii_home()` 将目录设为 `0700`，文件设为 `0600`（可通过 `SPARKII_HOME_MODE` 覆盖）
- 容器检测（Docker/Podman/LXC）跳过 chmod；managed 模式由 NixOS 激活脚本管理权限
- Docker 部署通过 `SPARKII_UID`/`SPARKII_GID` 强制 chown 子目录，避免多进程 uid-mapped 场景下的 `PermissionError`
- `.env` 文件加载后对以 `_API_KEY`/`_TOKEN`/`_SECRET`/`_KEY` 结尾的变量执行 ASCII 清洗，丢弃非 ASCII 字符并告警
- UTF-16 BOM 文件会被重写为 UTF-8；UTF-32 BOM 被拒绝（避免静默损坏）

### 3.5 外部 Secret 源集成

`env_loader._apply_external_secret_sources()` 调用 `agent.secret_sources.registry.apply_all()`，支持 Bitwarden、1Password 等后端，按“mapped-beats-bulk、first-claim-wins”规则合并，并在 UI 中标注来源（如 “(from Bitwarden)”）。

### 3.6 Gateway 配置叠加

`gateway/config.py` 通过 dataclass（`PlatformConfig`、`StreamingConfig`、`SessionResetPolicy`、`GatewayConfig`）承载网关特有配置，读取时优先走当前 secret scope 的 `_get_secret()`，单进程内支持 multiplex profiles。

## 4. 约定与约束

- **配置权威**：`config.yaml` 是唯一持久化配置源；`.env` 仅用于密钥；`terminal.*` 在 dotenv 重载后会由 config 重新桥接覆盖
- **受管安装禁止写配置**：`is_managed()` 为真时，任何写 `config.yaml` 的操作都会返回错误消息，引导用户使用 `nixos-rebuild switch`
- **配置解析失败不崩溃**：YAML 解析错误会备份到 `config.yaml.corrupt.<ts>.bak`，回退到 `DEFAULT_CONFIG`，并通过日志和 stderr 警告一次（基于 mtime/size 去重）
- **未知根键允许但记录**：`_KNOWN_ROOT_KEYS` 包含 `DEFAULT_CONFIG.keys()` 加 `_EXTRA_KNOWN_ROOT_KEYS`（如 `custom_providers`、`platforms`、`plugins`），新默认字段自动接受
- **Provider 别名兼容**：自定义 provider 支持 camelCase 键（`apiKey`→`api_key`、`baseUrl`→`base_url` 等）自动映射，但会发出一次性警告
- **Install method 检测**：通过代码树 `.install_method` 文件（而非 `$SPARKII_HOME`）判断 docker/nix/git/unknown，避免共享 home 导致的污染
- **配置版本 floor**：旧 schema（显式 `_config_version` < v12）会被拒绝，防止运行在新代码上加载过旧的配置结构
- **并发安全**：所有配置 I/O 通过 `_CONFIG_LOCK`（RLock）序列化，保护 libyaml 和进程级缓存
- **进程隔离**：`get_process_sparkii_home()` 区分进程级 SPARKII_HOME（multiplex 场景下每个 profile 独立），与全局 `get_sparkii_home()` 分离

## 5. 适用性说明

该配置系统贯穿 CLI、Gateway、TUI、Dashboard 及 cron 任务，是 Sparkii Agent 的核心基础设施之一，支撑多 profile、多平台、多 provider 的复杂运行时装配。