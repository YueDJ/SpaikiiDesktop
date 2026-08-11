# STDIO传输

<cite>
**本文引用的文件**
- [tools/mcp_tool.py](file://tools/mcp_tool.py)
- [agent/transports/](file://agent/transports/)
</cite>

## 目录
1. [简介](#简介)
2. [STDIO传输架构](#stdio传输架构)
3. [进程管理机制](#进程管理机制)
4. [消息传输协议](#消息传输协议)
5. [安全与资源控制](#安全与资源控制)
6. [配置与使用](#配置与使用)

## 简介
详细说明 STDIO 进程间通信传输方式的完整文档。详细说明连接建立和维护的建立机制，包括子进程管理、生命周期控制和安全参数。描述 STDIO 连接建立过程、消息交换协议、请求响应的自动重连机制。涵盖资源管理，包括进程资源管理、内存控制和日志记录。提供连接示例和连接配置、超时配置和进程管理配置的说明。描述安全考量，包括环境变量隔离、权限控制和沙箱隔离。包含连接建立和故障排查指南。

## STDIO传输架构

`mermaid
graph TB
    Agent["Agent 运行时"] --> MCPT["MCP 工具层<br/>tools/mcp_tool.py"]
    MCPT --> STDIO["STDIO 传输"]
    STDIO --> SP["子进程管理"]
    SP --> Server1["MCP Server 1"]
    SP --> Server2["MCP Server 2"]
    SP --> Server3["MCP Server 3"]
    STDIO --> JSONRPC["JSON-RPC 协议"]
    JSONRPC --> MSG["消息序列化/反序列化"]
`

**图示来源**
- [tools/mcp_tool.py:1-50](file://tools/mcp_tool.py#L1-L50)

## 进程管理机制

### 子进程生命周期

`mermaid
sequenceDiagram
    participant Agent as Agent 运行时
    participant MCP as MCP 工具层
    participant Subprocess as 子进程
    Agent->>MCP: 请求工具调用
    MCP->>Subprocess: 启动 MCP Server 进程
    Subprocess->>Subprocess: 初始化（加载配置）
    MCP->>Subprocess: 发送 JSON-RPC 请求
    Subprocess-->>MCP: 返回 JSON-RPC 响应
    MCP-->>Agent: 返回工具结果
    Note over MCP,Subprocess: 进程池保持连接，避免频繁启停
`

### 进程管理配置
`yaml
mcp:
  servers:
    - name: "filesystem"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
      timeout: 30
      max_retries: 3
      env:
        NODE_ENV: "production"
`

关键配置参数：
- **command**: 启动命令
- **args**: 命令参数列表
- **timeout**: 请求超时时间（秒）
- **max_retries**: 最大重试次数
- **env**: 环境变量

**章节来源**
- [tools/mcp_tool.py:100-200](file://tools/mcp_tool.py#L100-L200)

## 消息传输协议

### JSON-RPC 消息格式
`json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {"path": "/tmp/test.txt"}
  }
}
`

### 响应处理
- 成功响应包含 result 字段
- 错误响应包含 error 字段（code + message）
- 通知消息没有 id 字段

## 安全与资源控制
- **环境变量隔离**: 子进程仅继承必要环境变量
- **权限控制**: 使用最小权限原则运行子进程
- **资源限制**: 设置内存和 CPU 使用上限
- **超时控制**: 防止子进程无限阻塞

## 配置与使用

### 连接配置示例
`yaml
mcp:
  stdio:
    connection_timeout: 10
    read_timeout: 30
    write_timeout: 10
    max_message_size: "10MB"
    buffer_size: "64KB"
`

## 故障排查指南
- **连接超时**: 检查子进程启动命令和网络配置
- **消息丢失**: 检查缓冲区大小和消息完整性
- **进程崩溃**: 查看子进程日志和退出码
- **资源泄漏**: 监控进程数量和内存使用