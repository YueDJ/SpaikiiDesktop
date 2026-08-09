---
kind: dependency_management
name: 多语言依赖锁定与最小化安装策略（uv + npm workspaces + Nix/uv2nix）
category: dependency_management
scope:
    - '**'
source_files:
    - pyproject.toml
    - uv.lock
    - package.json
    - package-lock.json
    - .npmrc
    - .github/dependabot.yml
    - flake.nix
    - nix/python.nix
    - scripts/install.sh
    - constraints-termux.txt
---

## 1. 使用的系统与方法

仓库采用**多工具、分层式**的依赖管理方案，按语言生态分别治理：

- **Python**：使用 `pyproject.toml` + `uv.lock`（uv 包管理器），通过 `requires-python = ">=3.11,<3.14"` 限制解释器范围；所有核心依赖在 `dependencies` 中声明为**精确版本 pin**（`==X.Y.Z`），不允许可变范围。
- **Node.js**：使用 `package.json` + `package-lock.json`（npm v3 lockfile），并通过 **npm workspaces** 组织 `apps/*`、`ui-tui`、`web`、`tests-js` 等子项目；通过 `.npmrc` 的 `engine-strict=true` 和 `min-release-age=14` 强制新发布包至少 14 天才能进入依赖树。
- **Nix / 容器**：通过 `flake.nix` + `uv2nix` 将 `uv.lock` 转换为可复现的 Nix 虚拟环境，实现构建期与运行期的一致性；Docker 镜像基于此构建。
- **CI 更新**：仅对 `github-actions` 启用 Dependabot（`.github/dependabot.yml`），明确禁止对 pip/npm 依赖进行自动版本升级 PR。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `pyproject.toml` | Python 项目清单、精确版本依赖、可选 extras、`tool.uv` 覆盖与 `exclude-newer` |
| `uv.lock` | uv 解析后的完整依赖图（含每个包的 sdist/wheel URL 与 sha256 hash） |
| `package.json` | 根 npm workspace 配置、顶层依赖与 `overrides` |
| `package-lock.json` | npm 锁定的完整依赖树 |
| `.npmrc` | npm 引擎约束、安全漏洞临时豁免列表（`min-release-age-exclude[]`） |
| `.github/dependabot.yml` | 仅允许 github-actions 自动更新，禁止源码依赖自动升级 |
| `flake.nix` | Nix flake 入口，引入 `pyproject-nix`、`uv2nix`、`pyproject-build-systems` |
| `nix/python.nix` | 基于 `uv2nix` 构建 Python venv，支持 wheel-only 优先与 aarch64-darwin 预构建覆盖 |
| `scripts/install.sh` | 统一安装脚本：Linux/macOS 用 `uv`，Termux 回退到 stdlib venv + pip |
| `constraints-termux.txt` | Termux 环境的额外约束 |

## 3. 架构与约定

### 3.1 Python 依赖分层

- **核心依赖**（`dependencies`）：仅包含“每个 hermes 会话都会用到”的包，全部 `==X.Y.Z` 精确 pin。注释明确说明：范围依赖会允许 PyPI 在任何时候推送新版本而不经过代码审查，因此被禁止。
- **可选依赖**（`[project.optional-dependencies]`）：按功能域拆分为 `anthropic`、`messaging`、`voice`、`wake`、`google`、`web`、`mcp`、`acp`、`bedrock`、`vertex`、`azure-identity`、`termux`、`all` 等 extra，按需安装。
- **懒加载依赖**：大量 provider/skill 依赖（如 `mistralai`、`honcho`、`supermemory`、`mem0ai`、`opentelemetry-*`）不在 `[all]` 中，而是由 `tools/lazy_deps.py` 在首次使用时动态安装，避免上游污染破坏 fresh install。
- **平台标记**：大量依赖使用 `sys_platform == 'win32'`、`platform_system == 'Darwin'` 等平台条件限定安装范围。
- **transitive 覆盖**：通过 `tool.uv.override-dependencies` 强制修复上游未发布的漏洞（如 `pynacl>=1.6,<1.7`）。
- **时间门控**：`exclude-newer = "14 days"` 配合 `exclude-newer-package` 白名单，阻止过新的包进入解析。

### 3.2 Node.js 依赖治理

- **workspaces**：根 `package.json` 声明 `apps/*`、`ui-tui`、`web`、`tests-js` 为工作区，统一审计与脚本。
- **overrides**：通过 `overrides` 字段强制降级/升级脆弱传递依赖（`lodash`、`yauzl`、`protobufjs`、`brace-expansion`、`mermaid`、`dompurify`、`undici@^6`、`undici@^7`、`postcss` 等）。
- **allowScripts**：显式允许特定包的 `install` 脚本执行（`electron`、`node-pty`、`agent-browser` 等），其余默认拒绝。
- **engines**：强制 `node >= 22.22.0`、`npm < 11.10.0 || >= 11.17.0`。
- **min-release-age**：`.npmrc` 要求新发布包至少 14 天才能进入依赖树，但针对已知 CVE 修复提供大量 `min-release-age-exclude[]` 临时豁免。

### 3.3 Nix / uv2nix 集成

- `flake.nix` 引入 `pyproject-nix`、`uv2nix`、`pyproject-build-systems`，将 `uv.lock` 翻译为 Nix 包集合。
- `nix/python.nix` 使用 `sourcePreference = "wheel"` 优先使用二进制 wheel，并在 aarch64-darwin 上对 `numpy`、`onnxruntime`、`ctranslate2`、`faster-whisper` 等替换为 nixpkgs 预构建包。
- 通过 `HERMES_NIX_BUILD=1` 环境变量阻止在非 Nix 环境中构建 wheel。

### 3.4 安装路径

- `scripts/install.sh` 是统一入口：检测 OS 后选择 `uv`（桌面/服务器）或 `python -m venv + pip`（Termux）；支持 `--commit SHA` 精确安装、`--no-venv`、`--include-desktop` 等选项。
- Docker 镜像通过 `docker/entrypoint.sh` 调用安装流程。

## 4. 约定与约束

| 规则 | 来源/证据 |
|---|---|
| Python 核心依赖必须精确 pin（`==X.Y.Z`），禁止范围依赖 | `pyproject.toml` 顶部注释：“ranges allow PyPI to ship a fresh version … without a code review on our side” |
| 新增依赖需同步更新 `uv.lock`（`uv lock`） | 同上注释：“bump the version below AND regenerate uv.lock with `uv lock`” |
| 非核心依赖放入 optional extra，并由 `tools/lazy_deps.py` 懒加载 | `pyproject.toml` 各 extra 注释及 `[all]` 策略注释 |
| `[all]` 仅包含无法懒安装的依赖 | `pyproject.toml` `[all]` 注释：“Policy (2026-05-12): [all] includes only extras that genuinely CAN'T be lazy-installed” |
| 禁止 Dependabot 自动升级源码依赖（pip/npm） | `.github/dependabot.yml`：“We do NOT enable Dependabot for pip / npm / any source-dependency ecosystem” |
| 仅 github-actions 允许 Dependabot 自动更新 | `.github/dependabot.yml`：`package-ecosystem: "github-actions"` |
| Node 包新发布需等待 14 天 | `.npmrc`：`min-release-age=14` |
| 已知 CVE 修复可临时豁免 min-release-age | `.npmrc`：大量 `min-release-age-exclude[]` 条目 |
| Node 包 `install` 脚本默认禁止，需显式 `allowScripts` | `package.json`：`allowScripts` 仅放行少数包 |
| Python 解释器版本限制在 3.11–3.13 | `pyproject.toml`：`requires-python = ">=3.11,<3.14"` |
| Nix 构建优先 wheel，必要时回退到 nixpkgs 预构建 | `nix/python.nix`：`sourcePreference = "wheel"` + aarch64-darwin override |
| 禁止在非 Nix 环境构建 hermes-agent wheel | `nix/python.nix`：`HERMES_NIX_BUILD = "1"` 检查 |
| 安装脚本忽略继承的 `PYTHONPATH`/`PYTHONHOME` 防止模块遮蔽 | `scripts/install.sh`：`unset PYTHONPATH` / `PYTHONHOME` |
| Termux 使用独立约束文件 | `constraints-termux.txt` |

## 5. 总结

该仓库的依赖管理以**供应链安全**为核心目标：通过精确版本 pin、14 天发布冷却期、Dependabot 仅作用于 CI action、Nix/uv2nix 可复现构建、以及可选/懒加载依赖隔离脆弱上游，形成多层防护。任何依赖变更都需要人工评审并同步更新锁文件，而非自动化滚动升级。