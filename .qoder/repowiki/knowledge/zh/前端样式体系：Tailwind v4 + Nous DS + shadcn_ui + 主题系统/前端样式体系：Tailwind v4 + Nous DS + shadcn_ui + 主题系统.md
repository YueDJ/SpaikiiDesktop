---
kind: frontend_style
name: 前端样式体系：Tailwind v4 + Nous DS + shadcn/ui + 主题系统
category: frontend_style
scope:
    - '**'
source_files:
    - apps/desktop/src/styles.css
    - apps/desktop/src/themes/skin.ts
    - apps/desktop/src/themes/presets.ts
    - apps/desktop/src/themes/context.tsx
    - apps/desktop/src/themes/user-themes.ts
    - apps/desktop/src/themes/backend-sync.ts
    - apps/desktop/components.json
    - web/src/index.css
    - web/src/themes/context.tsx
    - web/src/themes/presets.ts
    - ui-tui/src/theme.ts
    - apps/desktop/package.json
    - web/package.json
---

## 1. 使用的系统与工具

仓库包含三个独立的前端应用，各自维护一套样式栈：

- **桌面应用（apps/desktop）**：基于 Electron + Vite + React，使用 Tailwind CSS v4（`@tailwindcss/vite`）、shadcn/ui（style: `new-york`，CSS 变量模式，baseColor: `neutral`）、`@nous-research/ui` 设计系统、`tw-shimmer` 闪烁动画、`@vscode/codicons` 图标、`katex` 数学公式渲染。
- **Web Dashboard（web）**：基于 Vite + React，同样使用 Tailwind CSS v4，通过 `@import '@nous-research/ui/styles/fonts.css'` 与 `globals.css` 引入 Nous Design System，并通过 `@source '../node_modules/@nous-research/ui/dist'` 扫描其组件以保留 JIT 生成的 utility 类。同时映射 shadcn 兼容 token（`--color-card`、`--color-muted-foreground` 等）供旧页面代码继续使用。
- **终端 TUI（ui-tui）**：纯 Node.js Ink 应用，无 CSS，通过 `ui-tui/src/theme.ts` 实现 ANSI 256 色/真彩主题的生成与适配，将皮肤种子（seeds）经 `deriveTones` 计算为完整调色板，并针对 Apple Terminal 的有限色深做 ansi256 归一化。

## 2. 关键文件

- `apps/desktop/src/styles.css`：桌面应用主样式入口，定义 `@theme inline` 中的 `--dt-*` / `--ui-*` 设计令牌、字体嵌入（Noto Sans SC、JetBrains Mono、Collapse）、暗色模式 `:root.dark` 覆盖、z-index 层级阶梯（`--z-modal-backdrop` → `--z-crash`）、`prefers-reduced-motion` 全局禁用、`.ref` 引用链接、`.arc-border` 动画边框等。
- `apps/desktop/src/themes/`：主题运行时——`skin.ts`、`presets.ts`、`context.tsx`、`user-themes.ts`、`backend-sync.ts`、`install.ts` 等，负责皮肤加载、用户自定义主题、与后端同步主题。
- `web/src/index.css`：Web 仪表盘样式入口，导入 Nous DS fonts/globals，声明 LENS_0（Sparkii Teal）默认主题变量，映射 shadcn 兼容 token，定义密度缩放（`--spacing` via `--theme-spacing-mul`）与 RTL 支持。
- `web/src/themes/`：Web 侧主题上下文与预设。
- `ui-tui/src/theme.ts`：TUI 主题引擎，定义 `ThemeSeeds` → `buildPalette` → `adaptColorsToBackground` → `fromSkin` 的完整管线，以及 `detectLightMode`、`normalizeThemeForAnsiLightTerminal` 等环境探测逻辑。
- `apps/desktop/components.json`：shadcn/ui 配置（style: new-york, cssVariables: true, iconLibrary: tabler）。
- `apps/desktop/package.json` / `web/package.json`：依赖声明（Tailwind v4、`@nous-research/ui`、Radix UI、xterm.js、motion 等）。

## 3. 架构与设计约定

### 桌面应用（Electron）
- **令牌分层**：`styles.css` 中 `:root` 定义 `--theme-*` 种子色（primary、midground、background-seed 等），再在 `@layer base` 中派生 `--ui-*` 语义层（`--ui-bg-chrome`、`--ui-bg-editor`、`--ui-text-primary` 等），最后映射到 shadcn/ui 所需的 `--dt-*` 变量，形成「种子 → 语义 → 组件」三层。
- **暗色模式**：通过 `:root.dark` 覆盖混合比例（`--theme-mix-chrome`、`--theme-mix-card` 等）和语义色，而非复制整份变量；`@custom-variant dark (&:is(.dark *))` 启用 Tailwind v4 的 dark variant。
- **z-index 阶梯**：集中定义 `--z-modal-backdrop` (120) → `--z-over-modal-content` (210) → `--z-connecting` (1200) 等，禁止组件内随意写死 z-index 字面量。
- **字体策略**：通过 `@font-face` 内嵌 Noto Sans SC（CJK）、JetBrains Mono（终端）、Collapse（品牌），避免依赖系统字体；`--dt-font-sans` / `--dt-font-mono` 作为统一引用点。
- **可访问性**：全局 `prefers-reduced-motion: reduce` 下将所有动画/过渡强制置零；focus ring 被全局移除（由组件级 glow 替代）。
- **主题切换**：`themes/` 目录提供 skin/preset/user-theme/backend-sync 机制，运行时通过 `applyTheme()` 注入 CSS 变量。

### Web Dashboard
- **Nous Design System**：通过 `@nous-research/ui` 提供现成组件与 tokens，`index.css` 仅做主题覆盖（LENS_0 深色主题）与 shadcn 兼容层。
- **密度缩放**：通过 `--theme-spacing-mul` 控制 Tailwind spacing scale，实现紧凑/舒适布局切换。
- **RTL 支持**：`html[dir="rtl"]` 块配合 Tailwind v4 逻辑间距（ms-/me-、ps-/pe-）自动翻转方向。

### 终端 TUI
- **种子→派生**：`ThemeSeeds`（accent、bg、text 等少量身份色）经 `deriveTones` 计算 muted/label/surface/activeRow/selection/border 等衍生色，保证任何皮肤都不会产生不协调的“dim”。
- **对比度保障**：`adaptColorsToBackground` 对前景色施加 WCAG 对比度下限（显示色 ≥1.45，语义色 ≥2.2），填充色按极性限制（light bg min luminance 0.4，dark bg max luminance 0.35），错误极性时回退到派生值。
- **ANSI 256 适配**：Apple Terminal 等非真彩终端上，前景色被量化为 `ansi256(N)`，通过 `normalizeThemeForAnsiLightTerminal` 处理。
- **主题来源**：`fromSkin(colors, branding, ...)` 将皮肤 JSON 转换为 `Theme`，优先级：皮肤字段 > 派生默认 > 基础种子（DARK_SEEDS/LIGHT_SEEDS）。

## 4. 约定与约束

- **桌面应用**：所有颜色必须走 `--ui-*` / `--dt-*` 变量，禁止在组件中硬编码十六进制色值（注释明确说明“TS never ships a hex”）。z-index 必须使用预定义的 `--z-*` 阶梯变量。动画需尊重 `prefers-reduced-motion`。字体通过 `@font-face` 内嵌或 `--dt-font-*` 引用。
- **Web Dashboard**：新页面应优先使用 `@nous-research/ui` 组件；遗留 shadcn 风格调用通过 `@theme inline` 中的 token 映射保持兼容，不应新增裸 shadcn 类名。
- **TUI**：皮肤不得直接指定派生色（muted、surface 等），应由 `deriveTones` 计算；如需覆盖，应通过 `completion_menu_bg`、`status_bar_*` 等语义字段。
- **跨端一致性**：桌面与 TUI 共享同一套「种子→派生」理念，TUI 的 `theme.ts` 注释明确说明它镜像了桌面应用的 `--theme-*` seeds → `--ui-*` color-mix ladder。
- **构建期**：Tailwind v4 通过 `@import 'tailwindcss'` 与 `@tailwindcss/vite` 插件启用，无需传统 `tailwind.config.*` 文件（desktop 的 `components.json` 中 tailwind.config 为空字符串即证明）。
- **图标**：桌面用 `@vscode/codicons` + Tabler Icons（shadcn 配置），Web 用 `lucide-react`，TUI 用 Unicode 字符（⚕、❯、┊ 等）。
- **测试**：每个主题子系统都有对应测试（`skin.test.ts`、`presets.test.ts`、`profile-theme.test.ts`、`user-themes.test.ts`、`vscode.test.ts`、`backend-sync.test.ts`、`web/src/themes/` 下的测试），确保主题派生逻辑不被破坏。