# 工具Schema设计

<cite>
**本文引用的文件**
- [tools/schema_sanitizer.py](file://tools/schema_sanitizer.py)
- [tools/registry.py](file://tools/registry.py)
- [plugins/plugin_utils.py](file://plugins/plugin_utils.py)
</cite>

## 目录
1. [简介](#简介)
2. [Schema基础格式](#schema基础格式)
3. [参数类型支持](#参数类型支持)
4. [Schema清理机制](#schema清理机制)
5. [属性键规范化](#属性键规范化)
6. [后端兼容性处理](#后端兼容性处理)
7. [最佳实践](#最佳实践)

## 简介
本文档详细说明Sparkii Agent中工具Schema的设计规范和实现机制。Schema定义了工具接受的参数格式，是模型与工具交互的契约。系统通过schema_sanitizer.py对Schema进行后处理，确保在不同LLM后端（OpenAI、Anthropic、本地推理等）上的兼容性。

## Schema基础格式

工具Schema遵循OpenAI Function Calling规范：

`json
{
  "type": "function",
  "function": {
    "name": "tool_name",
    "description": "工具描述",
    "parameters": {
      "type": "object",
      "properties": {
        "param1": {
          "type": "string",
          "description": "参数描述"
        }
      },
      "required": ["param1"]
    }
  }
}
`

`mermaid
graph TB
A["工具定义<br/>ToolEntry"] --> B["Schema结构"]
B --> C["parameters"]
C --> D["type: object"]
C --> E["properties"]
C --> F["required"]
E --> G["参数定义"]
G --> H["type"]
G --> I["description"]
G --> J["default"]
`

**图表来源**
- [tools/registry.py:201-231](file://tools/registry.py#L201-L231)
- [tools/schema_sanitizer.py:120-136](file://tools/schema_sanitizer.py#L120-L136)

## 参数类型支持

### 基本类型
- **string**: 字符串类型
- **number/integer**: 数值类型
- **boolean**: 布尔类型
- **array**: 数组类型
- **object**: 对象类型

### 复杂类型
- **嵌套对象**: properties内定义子对象
- **数组对象**: items中定义数组元素结构
- **枚举类型**: 使用enum约束值范围
- **联合类型**: anyOf/oneOf定义多类型

`python
# 示例：复杂参数Schema
{
    "type": "object",
    "properties": {
        "config": {
            "type": "object",
            "properties": {
                "debug": {"type": "boolean", "default": false},
                "output_format": {
                    "type": "string",
                    "enum": ["json", "text", "html"]
                }
            }
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["config"]
}
`

**章节来源**
- [tools/schema_sanitizer.py:240-271](file://tools/schema_sanitizer.py#L240-L271)

## Schema清理机制

sanitize_tool_schemas()函数对工具Schema进行深度清理，解决各种兼容性问题：

`mermaid
flowchart TD
A["输入Schema列表"] --> B["深拷贝"]
B --> C["_sanitize_single_tool"]
C --> D["_sanitize_node<br/>递归清理"]
D --> E["strip_nullable_unions<br/>折叠可空联合"]
E --> F["_strip_top_level_combinators<br/>移除顶层组合器"]
F --> G["_strip_ref_siblings<br/>清理$ref兄弟节点"]
G --> H["输出清理后Schema"]
`

### 清理规则

1. **裸字符串修复**: 将"object"转换为{"type": "object}
2. **空properties补充**: 为{"type": "object}添加properties: {}
3. **数组类型转换**: 将["string", "null"]转换为单一类型
4. **可空联合折叠**: 将anyOf: [{type: string}, {type: null}]折叠为非null分支
5. **顶层组合器移除**: 移除allOf/anyOf/oneOf/enum/not
6. **$ref兄弟清理**: 移除$ref节点旁的default关键字

`python
# 原始Schema（Pydantic生成）
{
    "anyOf": [
        {"type": "string"},
        {"type": "null"}
    ],
    "default": null
}

# 清理后Schema
{
    "type": "string",
    "nullable": true
}
`

**图表来源**
- [tools/schema_sanitizer.py:138-174](file://tools/schema_sanitizer.py#L138-L174)
- [tools/schema_sanitizer.py:240-271](file://tools/schema_sanitizer.py#L240-L271)

**章节来源**
- [tools/schema_sanitizer.py:1-40](file://tools/schema_sanitizer.py#L1-L40)
- [tools/schema_sanitizer.py:120-175](file://tools/schema_sanitizer.py#L120-L175)

## 属性键规范化

Anthropic等后端要求属性键匹配^[a-zA-Z0-9_.-]{1,64}$模式。系统提供自动重命名机制：

### 重命名流程

`python
def sanitize_property_key(key: str) -> str:
    new = _PROP_KEY_BAD_CHARS.sub("_", key)[:64]
    return new or "param"
`

### 反向映射

模型输出的参数键名需要反向映射回原始键名：

`python
def unrename_tool_args(params_schema, args):
    # 递归处理嵌套对象和数组
    ...
`

`mermaid
sequenceDiagram
participant M as "模型"
participant S as "Schema Sanitizer"
participant T as "工具处理器"
M->>S : 输出参数<br/>{issue_class_neq: "value"}
S->>T : 反向映射<br/>{issue_class~neq: "value"}
T-->>M : 处理结果
`

**图表来源**
- [tools/schema_sanitizer.py:56-117](file://tools/schema_sanitizer.py#L56-L117)

**章节来源**
- [tools/schema_sanitizer.py:56-87](file://tools/schema_sanitizer.py#L56-L87)
- [tools/schema_sanitizer.py:90-117](file://tools/schema_sanitizer.py#L90-L117)

## 后端兼容性处理

### 本地推理后端（llama.cpp）

llama.cpp的json-schema-to-grammar转换器对Schema有严格要求：

| 问题 | 修复方式 |
|------|----------|
| {"type": "object"} 无properties | 添加空properties |
| 裸字符串"object" | 转换为对象形式 |
| 数组类型["string", "null"] | 转换为单一类型 |
| 空properties的additionalProperties | 移除或限制 |

### Anthropic后端

- 拒绝anyOf/oneOf中的null分支
- 要求属性键符合正则模式
- 接受nullable: true标记

### OpenAI Codex后端

- 拒绝顶层allOf/anyOf/oneOf/enum/not
- 要求顶层必须是type: object

`python
# Codex后端要求的Schema结构
{
    "type": "object",
    "properties": {...},
    "required": [...]
    # 不能有allOf/anyOf等顶层关键字
}
`

**章节来源**
- [tools/schema_sanitizer.py:2-35](file://tools/schema_sanitizer.py#L2-L35)
- [tools/schema_sanitizer.py:177-237](file://tools/schema_sanitizer.py#L177-L237)

## 最佳实践

### Schema设计原则

1. **明确类型定义**: 始终指定明确的type字段
2. **提供description**: 为每个参数提供清晰描述
3. **合理使用required**: 标记必需参数
4. **设置default值**: 为可选参数提供默认值
5. **使用enum约束**: 限制参数取值范围

### 线程安全

Schema操作通过plugin_utils.py的线程安全单例模式保证并发安全：

`python
from plugins.plugin_utils import SingletonSlot

class SchemaProcessor(metaclass=SingletonSlot):
    _instance = None
    _lock = threading.Lock()
`

### 测试验证

`python
def test_sanitize_nullable_union():
    schema = {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": null
    }
    result = strip_nullable_unions(schema)
    assert result == {"type": "string", "nullable": true}
`

**章节来源**
- [tools/schema_sanitizer.py:1-40](file://tools/schema_sanitizer.py#L1-L40)
- [plugins/plugin_utils.py:1-136](file://plugins/plugin_utils.py#L1-L136)
- [tools/registry.py:562-645](file://tools/registry.py#L562-L645)
