# OAuth认证流程

<cite>
**本文引用的文件**
- [tools/mcp_oauth_manager.py](file://tools/mcp_oauth_manager.py)
- [tools/mcp_tool.py](file://tools/mcp_tool.py)
</cite>

## 目录
1. [简介](#简介)
2. [OAuth2.0授权码流程](#oauth20授权码流程)
3. [MCPOAuthManager架构](#mcpoauthmanager架构)
4. [动态客户端注册](#动态客户端注册)
5. [令牌管理机制](#令牌管理机制)
6. [跨进程令牌同步](#跨进程令牌同步)
7. [401去重机制](#401去重机制)
8. [故障排除](#故障排除)

## 简介

Sparkii Agent的MCP协议OAuth认证系统实现了完整的OAuth2.0授权码流程，支持动态客户端注册、令牌刷新和跨进程同步。本文档详细说明OAuth认证的工作原理、配置方法和故障排除指南。

## OAuth2.0授权码流程

MCP OAuth认证遵循标准的OAuth2.0授权码流程：

`mermaid
sequenceDiagram
participant Client as Sparkii Client
participant Auth as 授权服务器
participant Resource as MCP服务器
Client->>Auth: 1. 发现OAuth元数据
Auth-->>Client: 返回授权端点URL
Client->>Auth: 2. 重定向到授权页面
Auth-->>Client: 用户授权
Client->>Auth: 3. 用授权码交换令牌
Auth-->>Client: 返回access_token + refresh_token
Client->>Resource: 4. 使用access_token调用工具
Resource-->>Client: 返回工具结果
alt 令牌过期
Client->>Auth: 5. 用refresh_token刷新
Auth-->>Client: 返回新access_token
end
`

**图表来源**
- [tools/mcp_oauth_manager.py:1-33](file://tools/mcp_oauth_manager.py#L1-L33)

## MCPOAuthManager架构

MCPOAuthManager是OAuth状态的单一真相源，管理所有MCP服务器的OAuth提供者实例：

`python
class MCPOAuthManager:
    "单例管理器，管理每个MCP服务器的OAuth状态"
    
    def __init__(self):
        self._entries: dict[tuple[str, str], _ProviderEntry] = {}
        self._entries_lock = threading.Lock()
        self._inflight_tasks: set[asyncio.Task] = set()
`

### 核心组件

| 组件 | 职责 |
|------|------|
| _ProviderEntry | 每个服务器的OAuth状态容器 |
| SparkiiMCPOAuthProvider | OAuthClientProvider子类，注入磁盘监视钩子 |
| MCPOAuthManager | 进程级单例，协调所有OAuth操作 |

**章节来源**
- [tools/mcp_oauth_manager.py:446-500](file://tools/mcp_oauth_manager.py#L446-L500)

## 动态客户端注册

支持RFC 7591动态客户端注册，自动处理客户端注册和失效检测：

`mermaid
flowchart TD
Start[首次连接MCP服务器] --> Check{有存储的client_info?}
Check --> |否| Register[动态注册客户端]
Register --> Store[存储client.json]
Check --> |是| Use[使用现有客户端]
Use --> Auth[发起授权流程]
Store --> Auth
alt 授权失败invalid_client
Auth --> Poison[检测到失效客户端]
Poison --> Delete[删除client.json]
Delete --> Register
end
`

### 客户端元数据配置

`yaml
# config.yaml
mcp_servers:
  my_server:
    url: https://mcp.example.com
    oauth:
      client_name: Sparkii Agent
      redirect_uris: [http://localhost:3000/callback]
      grant_types: [authorization_code, refresh_token]
      scope: tools:execute
`

**章节来源**
- [tools/mcp_oauth_manager.py:322-388](file://tools/mcp_oauth_manager.py#L322-L388)

## 令牌管理机制

### 令牌存储

令牌存储在~/.sparkii/mcp-tokens/目录下，每个服务器一个JSON文件：

`json
{
  access_token: eyJ...,
  refresh_token: dGhpcw...,
  expires_at: 1699999999,
  token_type: Bearer,
  scope: tools:execute
}
`

### 令牌过期检测

SparkiiMCPOAuthProvider在每次请求前检查令牌有效性：

`python
async def _initialize(self) -> None:
    "加载令牌并设置过期时间"
    await super()._initialize()
    tokens = self.context.current_tokens
    if tokens is not None and tokens.expires_in is not None:
        self.context.update_token_expiry(tokens)
`

**章节来源**
- [tools/mcp_oauth_manager.py:149-225](file://tools/mcp_oauth_manager.py#L149-L225)

## 跨进程令牌同步

支持多个进程（如CLI、cron任务）同时使用同一MCP服务器的令牌：

### 磁盘监视机制

`python
async def invalidate_if_disk_changed(self, server_name: str) -> bool:
    "检查令牌文件是否被外部进程修改"
    tokens_path = _get_token_dir() / f{_safe_filename(server_name)}.json
    mtime_ns = tokens_path.stat().st_mtime_ns
    
    if mtime_ns != entry.last_mtime_ns:
        # 文件被修改，强制重新加载
        entry.provider._initialized = False
        return True
    return False
`

### 同步流程

`mermaid
sequenceDiagram
participant P1 as 进程1 (CLI)
participant Disk as 磁盘令牌文件
participant P2 as 进程2 (cron)
P1->>Disk: 写入新令牌
P2->>Disk: 检查mtime
Disk-->>P2: mtime已变更
P2->>P2: 重置_initialized
P2->>Disk: 重新加载令牌
`

**章节来源**
- [tools/mcp_oauth_manager.py:637-678](file://tools/mcp_oauth_manager.py#L637-L678)

## 401去重机制

当多个并发请求同时收到401错误时，只触发一次令牌刷新：

`python
async def handle_401(self, server_name: str, failed_access_token: str = None) -> bool:
    "处理401错误，跨并发调用去重"
    key = failed_access_token or <unknown>
    
    async with entry.lock:
        pending = entry.pending_401.get(key)
        if pending is None:
            # 第一个请求：创建Future并执行刷新
            pending = loop.create_future()
            entry.pending_401[key] = pending
            asyncio.create_task(_do_handle())
        # 其他请求：等待同一个Future
    
    return await pending
`

### 并发安全保证

1. **Future去重**：相同access_token的401共享同一个Future
2. **锁保护**：entry.lock防止竞态条件
3. **任务引用**：_inflight_tasks防止任务被GC回收

**章节来源**
- [tools/mcp_oauth_manager.py:682-760](file://tools/mcp_oauth_manager.py#L682-L760)

## 故障排除

### 非交互式环境

在无浏览器的环境中，需要预先完成授权：

`ash
# 交互式授权
sparkii mcp login <server_name>

# 检查令牌状态
sparkii mcp status <server_name>
`

### 令牌刷新失败

`ash
# 强制重新授权
sparkii mcp reauth <server_name>

# 清除缓存的客户端注册
sparkii mcp remove <server_name>
`

### 调试日志

`ash
# 启用OAuth调试日志
SPARKII_LOG_LEVEL=DEBUG sparkii mcp status <server_name>
`

**章节来源**
- [tools/mcp_oauth_manager.py:590-610](file://tools/mcp_oauth_manager.py#L590-L610)
