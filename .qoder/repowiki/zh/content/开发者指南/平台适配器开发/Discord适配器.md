# Discord适配器

<cite>
**本文引用的文件**
- [plugins/platforms/discord/](file://plugins/platforms/discord/)
- [gateway/platforms/base.py](file://gateway/platforms/base.py)
</cite>

## 目录
1. [简介](#简介)
2. [Discord Bot 功能](#discord-bot-功能)
3. [WebSocket 连接管理](#websocket-连接管理)
4. [消息事件处理](#消息事件处理)
5. [交互组件](#交互组件)
6. [OAuth2 认证](#oauth2-认证)
7. [配置与部署](#配置与部署)

## 简介
描述 Discord 平台适配器的完整文档。说明 Discord Bot 功能的完整实现，包括 WebSocket 连接管理、消息事件监听和解析、交互组件（Buttons、Select Menus）。详细描述 Discord 特有的功能，包括角色权限、频道管理支持、嵌入消息和文件上传、斜杠命令（Slash Commands）、线程（Threads）。说明适配器的通用通道支持和个性化格式。提供完整的 OAuth2 认证流程和权限配置示例。描述适配器的性能优化和可靠性改进。

## Discord Bot 功能

`mermaid
graph TB
    Discord["Discord API"] --> WS["WebSocket 连接"]
    WS --> Events["事件监听"]
    Events --> Message["消息事件"]
    Events --> Interaction["交互事件"]
    Events --> Slash["斜杠命令"]
    Message --> Handler["消息处理器"]
    Interaction --> Components["组件处理"]
    Slash --> CommandRouter["命令路由"]
    Handler --> Agent["Agent 运行时"]
    Components --> Agent
    CommandRouter --> Agent
`

**图示来源**
- [plugins/platforms/discord/__init__.py:1-50](file://plugins/platforms/discord/__init__.py#L1-L50)
- [gateway/platforms/base.py:1-50](file://gateway/platforms/base.py#L1-L50)

## WebSocket 连接管理
### 连接建立
`python
class DiscordGateway:
    async def connect(self):
        gateway_url = await self.get_gateway_url()
        self.ws = await websockets.connect(gateway_url)
        await self.identify()

    async def identify(self):
        await self.ws.send(json.dumps({
            "op": 2,
            "d": {
                "token": self.token,
                "intents": self.intents,
                "properties": {"os": "linux", "browser": "sparkii"}
            }
        }))
`

### 心跳机制
- 定期发送心跳包保持连接
- 检测连接断开并自动重连
- 处理 Gateway 重启事件

## 消息事件处理
### 消息接收
`python
async def on_message(self, message):
    if message.author.bot:
        return
    # 转换为内部格式
    internal_msg = self.convert_message(message)
    # 发送到 Agent
    response = await self.agent.process(internal_msg)
    # 发送回复
    await message.channel.send(response)
`

### 消息格式转换
- Discord 消息 -> 内部格式
- 支持富文本、嵌入、附件
- 处理特殊字符和编码

## 交互组件

### Buttons
`python
class Button(discord.ui.Button):
    async def callback(self, interaction):
        await interaction.response.send_message("Button clicked!")
`

### Select Menus
`python
class Select(discord.ui.Select):
    async def callback(self, interaction):
        selected = self.values[0]
        await interaction.response.send_message(f"Selected: {selected}")
`

## OAuth2 认证
`yaml
discord:
  client_id: "your_client_id"
  client_secret: "your_client_secret"
  redirect_uri: "http://localhost:8080/callback"
  scopes:
    - bot
    - applications.commands
  permissions:
    - Send Messages
    - Read Messages
    - Embed Links
`

## 配置与部署
`yaml
discord:
  token: ""
  prefix: "!"
  channels:
    - "general"
    - "ai-chat"
  features:
    slash_commands: true
    threads: true
    reactions: true
`

## 性能优化
- 连接池复用
- 消息批量处理
- 缓存策略
- 速率限制处理
