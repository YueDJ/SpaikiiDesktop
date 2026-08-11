# 主流AI提供商

<cite>
**本文引用的文件**
- [plugins/model-providers/anthropic/](file://plugins/model-providers/anthropic/)
- [plugins/model-providers/gemini/](file://plugins/model-providers/gemini/)
- [plugins/model-providers/xai/](file://plugins/model-providers/xai/)
- [plugins/model-providers/vertex/](file://plugins/model-providers/vertex/)
</cite>

## 目录
1. [简介](#简介)
2. [Anthropic Claude](#anthropic-claude)
3. [Google Gemini](#google-gemini)
4. [xAI Grok](#xai-grok)
5. [Google Vertex AI](#google-vertex-ai)
6. [认证机制对比](#认证机制对比)
7. [成本优化](#成本优化)

## 简介
描述主流 AI 提供商集成的详细文档。涵盖 Anthropic Claude、Google Gemini、xAI Grok、Google Vertex AI 等多个 AI 模型的技术架构。详细说明各提供商的独特功能特性，如 Claude 的思维链能力、Gemini 的多模态支持、Vertex 的企业级安全。描述认证机制差异，包括 OAuth、Service Account、Workload Identity 等。提供模型选择指导，帮助用户根据需求选择合适的提供商。提供实际部署经验，包括成本优化、延迟优化和可靠性保证。

## Anthropic Claude

### 特性
- 强大的推理和分析能力
- 长上下文支持（200K tokens）
- 工具调用和函数支持
- 安全性和可控性

### 配置
`yaml
providers:
  anthropic:
    api_key: ""
    model: "claude-3-opus-20240229"
    max_tokens: 4096
    temperature: 0.7
`

### 思维链能力
Claude 支持显式的思维链推理：
`python
response = await client.messages.create(
    model="claude-3-opus-20240229",
    messages=[{"role": "user", "content": "Solve this math problem..."}],
    thinking={"type": "enabled", "budget_tokens": 5000}
)
`

**章节来源**
- [plugins/model-providers/anthropic/__init__.py:1-50](file://plugins/model-providers/anthropic/__init__.py#L1-L50)

## Google Gemini

### 特性
- 多模态支持（文本、图像、视频、音频）
- 长上下文（1M tokens）
- 快速推理
- Google 生态集成

### 配置
`yaml
providers:
  gemini:
    api_key: ""
    model: "gemini-1.5-pro"
    safety_settings:
      - category: "HARM_CATEGORY_HARASSMENT"
        threshold: "BLOCK_ONLY_HIGH"
`

## xAI Grok

### 特性
- 实时信息访问
- 幽默和个性化风格
- X/Twitter 数据集成
- 快速响应

### 配置
`yaml
providers:
  xai:
    api_key: ""
    model: "grok-1"
    base_url: "https://api.x.ai/v1"
`

## Google Vertex AI

### 特性
- 企业级安全和合规
- 私有部署选项
- 自定义模型训练
- Google Cloud 集成

### 认证方式
`python
# Service Account 认证
from google.oauth2 import service_account
credentials = service_account.Credentials.from_service_account_file(
    'service-account.json',
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)
`

## 认证机制对比

| 提供商 | 认证方式 | 令牌管理 | 刷新机制 |
|--------|---------|---------|---------|
| Anthropic | API Key | 静态 | 手动轮换 |
| Gemini | API Key / OAuth | 静态/动态 | 自动刷新 |
| xAI | API Key | 静态 | 手动轮换 |
| Vertex | Service Account | 动态 | 自动刷新 |

## 成本优化
- **模型选择**: 根据任务复杂度选择合适的模型
- **缓存策略**: 缓存频繁请求的结果
- **批量处理**: 合并多个请求减少调用次数
- **提示词优化**: 减少不必要的 token 消耗
