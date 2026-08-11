# MCP服务器开发

<cite>
**本文引用的文件**
- [tools/mcp_tool.py](file://tools/mcp_tool.py)
- [plugins/mcp/](file://plugins/mcp/)
- [sparkii_cli/mcp_config.py](file://sparkii_cli/mcp_config.py)
</cite>

## 目录
1. [简介](#简介)
2. [MCP服务器架构](#mcp服务器架构)
3. [服务器配置规范](#服务器配置规范)
4. [工具注册机制](#工具注册机制)
5. [参数验证框架](#参数验证框架)
6. [错误处理模式](#错误处理模式)
7. [异步操作与资源管理](#异步操作与资源管理)
8. [安全最佳实践](#安全最佳实践)
9. [部署与集成](#部署与集成)

## 简介

Model Context Protocol (MCP) 是一种标准化的工具服务器协议，允许AI代理调用外部工具。本文档详细说明如何基于MCP协议开发工具服务器，包括服务器初始化、工具注册、参数验证和错误处理。

## MCP服务器架构

MCP服务器通过stdio、HTTP/StreamableHTTP或SSE传输协议与Sparkii Agent通信：

`mermaid
graph TB
subgraph  Sparkii Agent
Agent[Agent运行时]
Registry[工具注册表]
MCPClient[MCP客户端]
end
subgraph MCP服务器
Transport[传输层]
Router[路由层]
Tools[工具实现]
end
Agent --> Registry
Registry --> MCPClient
MCPClient --> |stdio/HTTP/SSE| Transport
Transport --> Router
Router --> Tools
Tools --> |JSON结果| MCPClient
MCPClient --> Agent
`

**图表来源**
- [tools/mcp_tool.py:67-95](file://tools/mcp_tool.py#L67-L95)

### 传输方式

| 传输方式 | 配置方式 | 适用场景 |
|----------|----------|----------|
| **stdio** | command + rgs | 本地子进程 |
| **HTTP** | url | 远程REST服务 |
| **SSE** | url + 	ransport: sse | 实时事件流 |

## 服务器配置规范

### config.yaml配置格式

`yaml
# ~/.sparkii/config.yaml
mcp_servers:
  # stdio传输示例
  filesystem:
    command: npx
    args: [-y, @modelcontextprotocol/server-filesystem, /tmp]
    env: {}
    timeout: 120
    connect_timeout: 60
    keepalive_interval: 10
  
  # HTTP传输示例
  remote_api:
    url: https://mcp-server.example.com/mcp
    headers:
      Authorization: Bearer sk-...
    timeout: 180
    skip_preflight: true
  
  # SSE传输示例
  searxng:
    url: http://localhost:8000/sse
    transport: sse
    timeout: 180
    connect_timeout: 10
`

### 配置参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| 	imeout | int | 300 | 单次工具调用超时（秒） |
| connect_timeout | int | 60 | 初始连接超时（秒） |
| keepalive_interval | int | 180 | 心跳间隔（秒） |
| idle_timeout_seconds | int | 3600 | 空闲回收超时 |
| max_lifetime_seconds | int | 86400 | 最大生命周期 |
| supports_parallel_tool_calls | bool | false | 并行工具调用支持 |

**章节来源**
- [tools/mcp_tool.py:1-66](file://tools/mcp_tool.py#L1-L66)

## 工具注册机制

MCP服务器通过	ools/list端点暴露可用工具，Sparkii Agent自动发现并注册：

`mermaid
sequenceDiagram
participant Agent as Sparkii Agent
participant Client as MCP客户端
participant Server as MCP服务器
Agent->>Client: 启动MCP连接
Client->>Server: 初始化连接
Server-->>Client: 返回capabilities
Client->>Server: tools/list请求
Server-->>Client: 返回工具定义列表
Client->>Agent: 注册到工具注册表
loop 工具调用
Agent->>Client: 调用工具(args)
Client->>Server: tools/call请求
Server-->>Client: 返回结果
Client-->>Agent: 返回结果
end
`

### 工具定义格式

MCP服务器返回的工具定义遵循JSON Schema：

`json
{
  name: read_file,
  description: 读取文件内容,
  inputSchema: {
    type: object,
    properties: {
      path: {
        type: string,
        description: 文件路径
      }
    },
    required: [path]
  }
}
`

**章节来源**
- [tools/mcp_tool.py:67-95](file://tools/mcp_tool.py#L67-L95)

## 参数验证框架

MCP服务器应实现严格的参数验证：

### 输入验证

`python
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server(my-server)

@server.tool()
async def read_file(path: str) -> list[TextContent]:
    if not path:
        raise ValueError(path is required)
    if .. in path:
        raise ValueError(Path traversal not allowed)
    content = await read_file_content(path)
    return [TextContent(type=text, text=content)]
`

### 类型约束

`json
{
  type: object,
  properties: {
    count: {
      type: integer,
      minimum: 1,
      maximum: 100
    },
    format: {
      type: string,
      enum: [json, text, csv]
    }
  }
}
`

## 错误处理模式

### 标准错误响应

`python
from mcp.types import TextContent

async def safe_tool_call(args):
    try:
        result = await execute(args)
        return [TextContent(type=text, text=json.dumps(result))]
    except FileNotFoundError as e:
        return [TextContent(
            type=text,
            text=json.dumps({error: str(e), code: FILE_NOT_FOUND})
        )]
    except Exception as e:
        return [TextContent(
            type=text,
            text=json.dumps({error: Internal error, code: INTERNAL})
        )]
`

### 错误码规范

| 错误码 | 说明 | HTTP等价 |
|--------|------|----------|
| INVALID_PARAMS | 参数验证失败 | 400 |
| NOT_FOUND | 资源不存在 | 404 |
| PERMISSION_DENIED | 权限不足 | 403 |
| INTERNAL | 服务器内部错误 | 500 |

## 异步操作与资源管理

### 异步处理模式

`python
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def managed_connection():
    conn = await create_connection()
    try:
        yield conn
    finally:
        await conn.close()

@server.tool()
async def long_running_task(args):
    async with managed_connection() as conn:
        result = await conn.execute(args)
        return [TextContent(type=text, text=result)]
`

### 连接池配置

`yaml
mcp_servers:
  database:
    url: https://db-mcp.example.com
    connection_pool:
      max_size: 10
      min_idle: 2
      max_idle_time: 300
`

## 安全最佳实践

### 环境变量过滤

stdio传输自动过滤敏感环境变量，阻止传递包含SECRET、API_KEY、TOKEN、PASSWORD等关键词的变量。

### 命令注入防护

使用白名单验证MCP服务器包名，避免直接拼接用户输入到命令参数中。

### 凭证剥离

错误消息中自动剥离Bearer令牌和API密钥等敏感信息。

**章节来源**
- [tools/mcp_tool.py:123-131](file://tools/mcp_tool.py#L123-L131)

## 部署与集成

### 本地开发测试

`ash
# 启动MCP服务器
npx @modelcontextprotocol/server-filesystem /tmp

# 测试连接
sparkii mcp test filesystem
`

### 与Sparkii集成

`ash
# 添加MCP服务器
sparkii mcp add filesystem --command npx --args -y,@modelcontextprotocol/server-filesystem,/tmp

# 列出已配置的服务器
sparkii mcp list

# 查看服务器状态
sparkii mcp status filesystem
`

**章节来源**
- [sparkii_cli/mcp_config.py](file://sparkii_cli/mcp_config.py)
