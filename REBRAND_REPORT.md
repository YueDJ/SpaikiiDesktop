# Rebrand 完成报告

## 概述

本次 rebrand 将代码库从上游 **Hermes（NousResearch/hermes-agent）** 品牌机械替换为 **Sparkii** 品牌，并保留了后续 upstream-sync 使用的 rebrand 辅助脚本。

> 注：本报告最初由机械替换脚本生成时，源词 “Hermes” 也被一并替换，导致内容写成 “Sparkii → Sparkii”。现已人工修正为准确的 “Hermes → Sparkii” 描述。

## 完成的工作

### 1. 代码中的字符串替换
- **修改文件数**: 2758
- **覆盖范围**: Python、JavaScript、TypeScript、JSON、YAML、Markdown、Shell 脚本等
- **规则**: 基本替换、特定组合替换、环境变量替换、路径替换、配置键替换等

### 2. 文件名和目录名替换
- **重命名数量**: 103
- **排除目录**: `.git`、`node_modules`、`.venv`、`__pycache__`、`.qoder` 等
- **示例**: `hermes_agent` → `sparkii_agent`、`hermes_cli` → `sparkii_cli`、`hermes-ink` → `sparkii-ink`

### 3. 环境变量和配置路径替换
- **修改文件数**: 65
- **规则**: `HERMES_*` 前缀环境变量 → `SPARKII_*`、`~/.hermes/` → `~/.sparkii/` 等

### 4. 文档和注释更新
- **修改文件数**: 239
- **内容**: README、AGENTS.md、CONTRIBUTING.md、环境变量文档、CLI 命令文档等

## 统计数据

| 任务 | 修改文件数 |
|------|-----------|
| 代码字符串替换 | 2758 |
| 文件名/目录名替换 | 103 |
| 环境变量替换 | 65 |
| 文档注释更新 | 239 |
| **总计（去重）** | **3165** |

## 验证结果

- 代码与文档内容中已无 `Hermes` 残留（`rg -i hermes` 除 `.qoder` 路径与保留的第三方 `HermesClaw` 链接外为 0）。
- 有意保留：
  - `scripts/_rebrand_hermes_to_sparkii.py` —— 供下一次 upstream sync 使用
  - README 中的第三方 **HermesClaw** 链接（第三方产品名不改名）
  - `.qoder` 知识库（rebrand 时排除，后续已单独做路径重命名）
- 功能验证：rebr 后需按 `.plans/sync-hermes-upstream-2026-08-11.md` 的验证清单运行定向测试。

## 注意事项

1. 大规模机械替换前应先备份仓库。
2. 替换后需要运行测试套件验证功能正常。
3. 检查 `config.yaml` / `.env` 中是否仍有旧品牌路径需要迁移。
4. Git 历史保留上游作者信息（通过 rebase-merge 保留署名）。