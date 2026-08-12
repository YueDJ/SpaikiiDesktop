<p align="center">
  <img src="assets/banner.png" alt="Sparkii Agent" width="100%">
</p>

# Sparkii Agent ☤

<p align="center">
  <a href="https://github.com/YueDJ/SparkiiDesktop"><img src="https://img.shields.io/badge/Repo-YueDJ%2FSparkiiDesktop-FFD700?style=for-the-badge" alt="Repository"></a>
  <a href="https://github.com/YueDJ/SparkiiDesktop/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/NousResearch/sparkii-agent"><img src="https://img.shields.io/badge/Upstream-Nous%20Research%20Sparkii-blueviolet?style=for-the-badge" alt="Upstream"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/Lang-English-lightgrey?style=for-the-badge" alt="English"></a>
  <a href="README.ur-pk.md"><img src="https://img.shields.io/badge/Lang-اردو-green?style=for-the-badge" alt="اردو"></a>
</p>

**自进化 AI 代理——[Nous Research](https://github.com/NousResearch/sparkii-agent) 的 Sparkii 代理的个人分支。** 它内置学习闭环——从经验中创建技能，在使用中改进技能，主动持久化知识，搜索过往对话，并在跨会话中逐步构建对你的深度理解。可以在 $5 的 VPS 上运行，也可以在 GPU 集群上运行，或者使用几乎零成本的 Serverless 基础设施。本分支已移除消息平台网关；CLI、TUI 和桌面应用是支持的界面。

支持任意模型——[Nous Portal](https://portal.nousresearch.com)、[OpenRouter](https://openrouter.ai)（200+ 模型）、[NVIDIA NIM](https://build.nvidia.com)（Nemotron）、[小米 MiMo](https://platform.xiaomimimo.com)、[z.ai/GLM](https://z.ai)、[Kimi/Moonshot](https://platform.moonshot.ai)、[MiniMax](https://www.minimax.io)、[Hugging Face](https://huggingface.co)、OpenAI，或自定义端点。使用 `sparkii model` 即可切换——无需改代码，无锁定。

<table>
<tr><td><b>真正的终端界面</b></td><td>完整的 TUI，支持多行编辑、斜杠命令自动补全、对话历史、中断重定向和流式工具输出。</td></tr>
<tr><td><b>闭环学习</b></td><td>代理管理记忆并定期自我提醒。复杂任务后自动创建技能。技能在使用中自我改进。FTS5 会话搜索配合 LLM 摘要实现跨会话回溯。<a href="https://github.com/plastic-labs/honcho">Honcho</a> 辩证式用户建模。兼容 <a href="https://agentskills.io">agentskills.io</a> 开放标准。</td></tr>
<tr><td><b>定时自动化</b></td><td>内置 cron 调度器，支持向任何平台投递。日报、夜间备份、周审计——全部用自然语言描述，无人值守运行。</td></tr>
<tr><td><b>委派与并行</b></td><td>生成隔离子代理处理并行工作流。编写 Python 脚本通过 RPC 调用工具，将多步管道压缩为零上下文开销的轮次。</td></tr>
<tr><td><b>随处运行</b></td><td>六种终端后端——本地、Docker、SSH、Daytona、Singularity 和 Modal。Daytona 和 Modal 提供 Serverless 持久化——代理环境空闲时休眠、按需唤醒，空闲期间几乎零成本。$5 VPS 或 GPU 集群都能跑。</td></tr>
<tr><td><b>研究就绪</b></td><td>批量轨迹生成、轨迹压缩——用于训练下一代工具调用模型。</td></tr>
</table>

---

## 快速安装

```bash
curl -fsSL https://raw.githubusercontent.com/YueDJ/SparkiiDesktop/main/scripts/install.sh | bash
```

支持 Linux、macOS、WSL2 和 Android (Termux)。安装程序会自动处理平台特定的配置。

> **Android / Termux：** 已测试的手动安装路径请参考 [Termux 指南](website/docs/getting-started/termux.md)。在 Termux 上，Sparkii 会安装精选的 `.[termux]` 扩展，因为完整的 `.[all]` 扩展会拉取 Android 不兼容的语音依赖。
>
> **Windows：** 在 PowerShell 中运行：
> ```powershell
> iex (irm https://raw.githubusercontent.com/YueDJ/SparkiiDesktop/main/scripts/install.ps1)
> ```
> 安装完成后，可能需要重启终端，然后运行 `sparkii` 开始对话。

安装后：

```bash
source ~/.bashrc    # 重新加载 shell（或: source ~/.zshrc）
sparkii              # 开始对话！
```

---

## 快速入门

```bash
sparkii              # 交互式 CLI — 开始对话
sparkii model        # 选择 LLM 提供商和模型
sparkii tools        # 配置启用的工具
sparkii config set   # 设置单个配置项
sparkii gateway      # 启动网关（webhook / API server）
sparkii setup        # 运行完整设置向导（一次性配置所有内容）
sparkii claw migrate # 从 OpenClaw 迁移（如果来自 OpenClaw）
sparkii update       # 更新到最新版本
sparkii doctor       # 诊断问题
```

📖 **[完整文档 →](website/docs/)**

---

## 省去到处收集 API Key — Nous Portal

Sparkii 始终允许你使用任意服务商，这点不会改变。但如果你不想为模型、网页搜索、图像生成、TTS、云浏览器分别去申请五个不同的 API Key，**[Nous Portal](https://portal.nousresearch.com)** 用一个订阅就能覆盖全部：

- **300+ 模型** — 用 `/model <name>` 随时切换
- **Tool Gateway** — 网页搜索（Firecrawl）、图像生成（FAL）、文本转语音（OpenAI）、云浏览器（Browser Use），全部通过订阅托管。无需额外注册任何账户。

全新安装时一条命令即可：

```bash
sparkii setup --portal
```

它会通过 OAuth 登录、把 Nous 设为推理服务商，并启用 Tool Gateway。随时用 `sparkii portal info` 查看路由状态。完整说明见 [Tool Gateway 文档](website/docs/user-guide/features/tool-gateway.md)。

你随时可以按工具单独切回自己的 API Key — Gateway 是按工具粒度生效的，不是一刀切。

---

## CLI 与消息平台 快速对照

用 `sparkii` 启动终端 UI——CLI、TUI 与桌面应用共享同一套斜杠命令。

| 操作 | CLI |
|------|-----|
| 开始对话 | `sparkii` |
| 开始新对话 | `/new` 或 `/reset` |
| 更换模型 | `/model [provider:model]` |
| 设置人格 | `/personality [name]` |
| 重试或撤销上一轮 | `/retry`、`/undo` |
| 压缩上下文 / 查看用量 | `/compress`、`/usage`、`/insights [--days N]` |
| 浏览技能 | `/skills` 或 `/<skill-name>` |
| 中断当前工作 | `Ctrl+C` 或发送新消息 |

完整命令列表请参阅 [CLI 指南](website/docs/user-guide/cli.md)。

---

## 文档

所有文档位于本仓库的 [website/docs](website/docs/) 目录：

| 章节 | 内容 |
|------|------|
| [快速开始](website/docs/getting-started/quickstart.md) | 安装 → 设置 → 2 分钟内开始首次对话 |
| [CLI 使用](website/docs/user-guide/cli.md) | 命令、快捷键、人格、会话 |
| [配置](website/docs/user-guide/configuration.md) | 配置文件、提供商、模型、所有选项 |
| [安全](website/docs/user-guide/security.md) | 命令审批、容器隔离 |
| [工具与工具集](website/docs/user-guide/features/tools.md) | 40+ 工具、工具集系统、终端后端 |
| [技能系统](website/docs/user-guide/features/skills.md) | 过程记忆、技能中心、创建技能 |
| [记忆](website/docs/user-guide/features/memory.md) | 持久记忆、用户画像、最佳实践 |
| [MCP 集成](website/docs/user-guide/features/mcp.md) | 连接任意 MCP 服务器扩展能力 |
| [定时调度](website/docs/user-guide/features/cron.md) | 定时任务与平台投递 |
| [上下文文件](website/docs/user-guide/features/context-files.md) | 影响每次对话的项目上下文 |
| [架构](website/docs/developer-guide/architecture.md) | 项目结构、代理循环、关键类 |
| [贡献](website/docs/developer-guide/contributing.md) | 开发设置、PR 流程、代码风格 |
| [CLI 参考](website/docs/reference/cli-commands.md) | 所有命令和标志 |
| [环境变量](website/docs/reference/environment-variables.md) | 完整环境变量参考 |

---

## 从 OpenClaw 迁移

如果你来自 OpenClaw，Sparkii 可以自动导入你的设置、记忆、技能和 API 密钥。

**首次安装时：** 安装向导（`sparkii setup`）会自动检测 `~/.openclaw` 并在配置开始前提供迁移选项。

**安装后任意时间：**

```bash
sparkii claw migrate              # 交互式迁移（完整预设）
sparkii claw migrate --dry-run    # 预览将要迁移的内容
sparkii claw migrate --preset user-data   # 仅迁移用户数据，不含密钥
sparkii claw migrate --overwrite  # 覆盖已有冲突
```

导入内容：
- **SOUL.md** — 人格文件
- **记忆** — MEMORY.md 和 USER.md 条目
- **技能** — 用户创建的技能 → `~/.sparkii/skills/openclaw-imports/`
- **命令白名单** — 审批模式
- **消息设置** — 平台配置、允许用户、工作目录
- **API 密钥** — 白名单中的密钥（OpenRouter、OpenAI、Anthropic、ElevenLabs）
- **TTS 资产** — 工作区音频文件
- **工作区指令** — AGENTS.md（使用 `--workspace-target`）

使用 `sparkii claw migrate --help` 查看所有选项，或使用 `openclaw-migration` 技能进行交互式代理引导迁移（含干运行预览）。

---

## 贡献

欢迎贡献！请参阅 [贡献指南](website/docs/developer-guide/contributing.md) 了解开发设置、代码风格和 PR 流程。

贡献者快速开始——使用标准安装器，然后在它创建的完整 git checkout 中开发：
`$SPARKII_HOME/sparkii-agent`（通常是 `~/.sparkii/sparkii-agent`）。这会匹配
`sparkii update`、托管 venv、lazy dependencies、gateway 和 docs tooling 使用的布局。

```bash
curl -fsSL https://raw.githubusercontent.com/YueDJ/SparkiiDesktop/main/scripts/install.sh | bash
cd "${SPARKII_HOME:-$HOME/.sparkii}/sparkii-agent"
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

手动克隆备用路径（用于一次性 clone / CI，或你明确不想使用 managed install layout 时）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv venv --python 3.11
source venv/bin/activate
uv pip install -e ".[all,dev]"
python -m pytest tests/ -q
```

---

## 社区

- 📚 [技能中心](https://agentskills.io)
- 🐛 [问题反馈](https://github.com/YueDJ/SparkiiDesktop/issues)
- 💡 [讨论区](https://github.com/YueDJ/SparkiiDesktop/discussions)
- 🔌 [___SPARKIICLAW_PRESERVE___](https://github.com/AaronWong1999/___SPARKIICLAW_URL_PRESERVE___) — 社区微信桥接：在同一微信账号上运行 Sparkii Agent 和 OpenClaw。

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)。

由 [Nous Research](https://github.com/NousResearch/sparkii-agent) 开发，[YueDJ](https://github.com/YueDJ) 维护的个人分支。
