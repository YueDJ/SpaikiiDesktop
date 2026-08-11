---
kind: build_system
name: 多语言构建、容器化与 CI/CD 流水线
category: build_system
scope:
    - '**'
source_files:
    - Dockerfile
    - docker-compose.yml
    - pyproject.toml
    - setup.py
    - flake.nix
    - nix/packages.nix
    - nix/python.nix
    - .github/workflows/ci.yml
    - scripts/install.sh
    - uv.lock
    - package-lock.json
---

## 1. 使用的构建系统与方法

本项目是一个 Python + Node.js 的混合仓库，采用多种构建工具并存的方式：

- **Python 包管理**：以 `pyproject.toml` 为单一声明源，使用 `uv`（astral-sh）进行依赖解析与安装；通过 `[project.optional-dependencies]` 定义可选功能集（`anthropic`、`messaging`、`web`、`all` 等），核心依赖全部精确锁定到 `==X.Y.Z`，避免上游漂移。
- **Node.js 前端构建**：根级 `package.json` + `package-lock.json` 管理 monorepo（`web/`、`ui-tui/`、`apps/*`），通过 `npm ci` / `npm run build` 分别构建 Web Dashboard 和 TUI 产物。
- **Docker 镜像**：单文件 `Dockerfile` 使用多阶段构建——先编译固定版本的 SQLite（修复 WAL-reset bug）、再拷贝 Node 26 与 uv 二进制，最后按层缓存 Python/Node 依赖并 `uv sync --frozen` 安装生产依赖，最终用 s6-overlay 作为 PID 1 进程管理器。
- **Nix 开发环境**：`flake.nix` + `nix/packages.nix` + `pyproject-nix` + `uv2nix` 提供可复现的开发 shell、NixOS 模块与打包表达式；`setup.py` 在 Nix 外主动阻止 `bdist_wheel`/`sdist`，强制所有分发走 installer/Docker/Nix 三通道。
- **Shell 安装器**：`scripts/install.sh`（Linux/macOS/Termux）与 `install.ps1`（Windows）负责探测系统、安装 uv/Python/Node、克隆仓库、创建 venv、安装依赖、配置 FHS 布局（root 下 `/usr/local/lib/sparkii-agent`）。
- **CI/CD**：`.github/workflows/ci.yml` 作为编排入口，调用子工作流执行 Python 测试、lint、JS 检查、Docker 构建、supply-chain 扫描、OSV 扫描、installer 测试等，并通过 `detect-changes` action 做变更影响分析，仅运行受影响的 lane。

## 2. 关键文件与位置

| 类别 | 关键文件 |
|---|---|
| Python 包元数据 | `pyproject.toml`、`setup.py` |
| 依赖锁定 | `uv.lock`、`package-lock.json` |
| Docker 镜像 | `Dockerfile`、`docker-compose.yml`、`docker/*.sh` |
| Nix 构建 | `flake.nix`、`nix/packages.nix`、`nix/python.nix`、`nix/devShell.nix` |
| 安装脚本 | `scripts/install.sh`、`install.cmd`、`install.ps1` |
| CI 编排 | `.github/workflows/ci.yml` 及同目录下各子 workflow |
| 版本信息 | `pyproject.toml` 中 `version = "0.20.0"` |

## 3. 架构与设计约定

### 分层缓存策略
Dockerfile 严格按“manifest → deps → source”顺序 COPY，使 Python 依赖层（`uv sync --frozen --no-install-project`）和前端构建层（`web && npm run build`、`ui-tui && npm run build`）独立缓存，源码改动不触发冷重建。

### 依赖隔离与最小化
- 核心依赖集中在 `pyproject.toml[dependencies]`，平台/后端相关依赖放入 optional extras（如 `anthropic`、`matrix`、`voice`），默认 `[all]` 仅包含真正无法 lazy-install 的集合。
- 运行时懒加载：`tools/lazy_deps.py` 在首次使用时按需安装第三方 SDK，避免一个上游污染破坏全量安装。
- 所有直接依赖使用 `==` 精确锁定，注释明确说明这是供应链安全策略（Mini Shai-Hulud worm 事件后强化）。

### 容器进程模型
- s6-overlay 作为 PID 1，管理 main sparkii、dashboard、per-profile gateway 三个服务。
- `entrypoint-dispatch.sh` 兼容被外部 init（Fly Machines、`docker run --init`）包裹的场景，回退到 `stage2-hook.sh` + `main-wrapper.sh` 路径。
- 非 root 用户 `sparkii`（UID 10000），数据目录 `/opt/data` 通过 volume 持久化。

### 安装布局
- 普通用户：`~/.sparkii/sparkii-agent`，命令链接到 `~/.local/bin/sparkii`。
- Linux root：FHS 布局 `/usr/local/lib/sparkii-agent` + `/usr/local/bin/sparkii`，数据仍在 `$SPARKII_HOME`。
- Termux：代码留在 `$SPARKII_HOME/sparkii-agent`，命令链接到 `$PREFIX/bin`。

### 版本与发布
- Python 版本约束 `>=3.11,<3.14`（防止 uv 自动选择 3.14 导致 Rust 依赖无 wheel）。
- Node 版本统一为 26（Dockerfile 注释标注 pin 在多处）。
- 构建时注入 `SPARKII_GIT_SHA` 到 `.hermes_build_sha`，供 `sparkii dump` 报告实际 commit。

## 4. 约定与约束

- **禁止裸 pip/pip install**：`setup.py` 在非 Nix 环境下抛出错误，强制走 installer/Docker/Nix 三种受控分发渠道。
- **依赖必须精确锁定**：`pyproject.toml` 中每个直接依赖都写死 `==X.Y.Z`，更新需同步修改版本号并重新生成 `uv.lock`。
- **CI 门禁**：PR 必须通过 `all-checks-pass` gate job（tests、lint、js-tests、docker-lint、supply-chain、osv-scanner 等聚合结果）；分支保护要求该单一 check。
- **变更检测驱动并行**：`detect-changes` action 输出 python/frontend/site/docker_meta 等布尔值，下游 job 据此跳过无关任务，减少 runner 占用。
- **Docker 构建不可变**：`COPY --chmod=a+rX,go-w . .` 将源码层设为只读，配合 `SPARKII_LAZY_INSTALL_TARGET=/opt/data/lazy-packages` 确保运行时只能向数据卷写入。
- **Nix 沙箱构建**：`SPARKII_NIX_BUILD=1` 环境变量是绕过 `setup.py` 构建守卫的唯一合法方式，由 `nix/python.nix` 设置。
- **Playwright 浏览器预装**：构建期安装 Chromium 到 `/opt/sparkii/.playwright`，避开运行时 `/opt/data` 挂载覆盖导致的丢失问题。
- **s6-overlay 校验**：下载 tarball 时使用 SHA256 校验（`S6_OVERLAY_*_SHA256` ARG），拒绝未签名/篡改的二进制。
- **SQLite 固定版本**：从源码编译 SQLite 3.53.4（带 FTS5 trigram 自测），替换系统 libsqlite3.so.0，规避 Debian trixie 的 WAL-reset bug。