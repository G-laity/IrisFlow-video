---
name: tool-creation
description: 将任意外部 API 或数据源封装为 IrisFlow 的 MCP 工具，含完整开发→测试→注册工作流。适用于 GitHub、天气、数据库等所有支持 HTTP 的外部服务。
---

# 外部 API 转 MCP 工具

## 触发条件

用户说 "封装工具"、"创建 MCP 工具"、"把 XX API 封装成工具"、"添加新工具"、"wrap API as tool"、"create MCP tool" 或类似表述。

## 流程

### 1. 分析数据源

与用户确认数据源类型后，确定工具的原子粒度：

- **一个工具只做一件事** — 如"搜索仓库"和"获取仓库详情"是两个独立工具
- **覆盖核心查询场景** — 优先实现高频使用的读操作（搜索、列表、详情），写操作按需添加
- **参数设计** — 每个工具的最小必需参数集：
  - `required` 中只放真正不可或缺的参数
  - 筛选条件（排序、分页、状态）作为可选参数
  - 使用 `enum` 约束固定选项（如 `["open", "closed", "all"]`）
  - 使用 `minimum`/`maximum` 约束数字范围
  - 所有参数提供 `default` 默认值

### 2. 编写 ToolDefinition

ToolDefinition 是 LLM 选择工具的**唯一依据**，质量直接决定调用准确率。

**5 条原则：**

| 原则 | 说明 | 反面案例 |
|------|------|----------|
| 说清何时用 | 适用/不适用场景，与相似工具的边界 | "查询数据库" |
| 说清有什么 | 告知返回内容结构、字段含义 | "返回查询结果" |
| 约束参数 | `enum` / `minimum` / `maximum` 代替自由文本 | 用 `string` 描述排序方式 |
| 给默认值 | 减少 LLM 猜参数的负担 | 每个参数都 required |
| 注明副作用 | 写操作、收费 API、频率限制必须前置声明 | 静默发邮件/删数据 |

**模板：**

```python
ToolDefinition(
    name="data_source_action",  # snake_case，以数据源为前缀
    description=(
        "【一句话摘要】详细说明工具的功能。"
        "适用场景：A、B、C。"
        "不适用：X → 用 other_tool。"
        "返回内容：字段1、字段2、字段3。"
        "注意：频率限制/认证要求/副作用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {
                "type": "integer",
                "description": "...",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": ["param1"],
    },
)
```

### 3. 实现 MCP 服务器

在 `backend/mcp_servers/` 下创建新的 `.py` 文件。

**最小骨架：**

```python
"""XXX API MCP 服务器。"""

from __future__ import annotations
import os
from typing import Any
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="XXX MCP Server", version="0.1.0")

# ── 工具处理器 ──
async def _my_tool(param1: str) -> str:
    """工具实现。"""
    ...

# ── 工具注册表 ──
TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "my_tool": {
        "definition": { ... },
        "handler": _my_tool,
    },
}

# ── MCP 端点 ──
@app.get("/tools/list")
async def list_tools():
    tools = [entry["definition"] for entry in TOOL_REGISTRY.values()]
    return {"tools": tools}

@app.post("/tools/call")
async def call_tool(request: Request):
    body = await request.json()
    tool_name = body.get("name", "")
    arguments = body.get("arguments", {})
    entry = TOOL_REGISTRY.get(tool_name)
    ...
    result = await handler(**arguments)
    return {"content": [{"text": result}]}
```

**关键约定：**

- 所有 handler 返回 `str`（文本格式的 LLM 友好输出，不是 JSON）
- **错误通过抛出异常处理**，不要返回 `[错误]` 前缀的字符串。
  `ToolExecutor` 会自动捕获异常并设置 `is_error=True`，前端据此展示错误样式。
  MCP 服务器的 `call_tool` 端点应在异常情况下返回 `{"content": [{"text": "错误原因"}], "isError": true}`。
- 返回内容做截断：文件 ≤8000 字符，列表 ≤20 条
- 使用 `httpx.AsyncClient`（项目已有依赖），超时设 8s
- 认证凭据从 `os.environ` 读取，不写进代码
- **⚠️ MCP 协议关键：工具定义的参数 Schema 字段名必须是 `inputSchema`，不是 `parameters`！**
  IrisFlow 的 MCP 客户端 (`mcp.py`) 读取 `t.get("inputSchema", {})`，
  如果用了 `parameters`，LLM 将看到空的参数 Schema，无法正确调用工具。

**可参考内置工具实现：**
- `backend/llm/tools/web_search.py` — 外部 API 调用 + 重试 + 异常抛出
- `backend/llm/tools/open_url.py` — httpx 下载 + trafilatura 提取 + 超时处理

### 4. 本地测试

**启动服务器：**

```bash
cd backend
# 设置所需的环境变量
export API_KEY=xxx  # Linux/Mac
set API_KEY=xxx     # Windows

uv run uvicorn mcp_servers.xxx_server:app --port 91XX
```

**测试工具发现：**

```bash
curl http://localhost:91XX/tools/list | python -m json.tool
# 期望：{"tools": [{"name": "my_tool", "description": "...", "inputSchema": {...}}]}
```

**测试单次调用：**

```bash
curl -X POST http://localhost:91XX/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"my_tool","arguments":{"param1":"test"}}'
# 期望：{"content": [{"text": "..."}]}
```

**测试错误处理：**

```bash
# 缺少必需参数
curl -X POST http://localhost:91XX/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"my_tool","arguments":{}}'
# 期望：{"content": [{"text": "缺少必需参数: param1"}], "isError": true}

# 未知工具
curl -X POST http://localhost:91XX/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"nonexistent","arguments":{}}'
# 期望：{"content": [{"text": "未知工具: nonexistent。可用工具: ..."}], "isError": true}
```

**类型检查：**

```bash
cd backend && uv run pyright mcp_servers/ --project pyrightconfig.json
# 期望：0 errors, 0 warnings
```

### 5. 注册到 IrisFlow

**方式一：API 注册（HTTP 服务器）**

```bash
curl -X PUT http://localhost:8000/api/mcp/config \
  -H "Content-Type: application/json" \
  -d '{"config": "{\"mcpServers\":{\"my-service\":{\"transport\":\"http\",\"url\":\"http://localhost:91XX\"}}}"}'
```

**方式二：API 注册（stdio 子进程）**

```bash
curl -X PUT http://localhost:8000/api/mcp/config \
  -H "Content-Type: application/json" \
  -d '{"config": "{\"mcpServers\":{\"my-service\":{\"command\":\"npx\",\"args\":[\"-y\",\"@myscope/my-server\"]}}}"}'
```

**方式三：前端设置面板**
1. 打开 IrisFlow → 设置 → MCP 标签页
2. 编辑 JSON 配置，添加服务器条目
3. 保存（后端自动 diff 重连，无需重启）

**验证注册：**
- 后端日志：`INFO  llm.mcp  MCP 'my-service' 已连接 (HTTP): ...`
- `GET /api/mcp/config` 应返回已注册的配置
- `GET /api/tools` 应列出 MCP 服务器提供的工具

### 6. 端到端验证

在 IrisFlow 中创建新对话，启用工具模式，发送明确的触发消息：

```
请使用 my_tool 工具，查询 ...
```

观察 WorkflowLog 中：
- ✅ 工具是否被正确调用（名称、参数）
- ✅ 返回结果是否正确展示
- ✅ 错误情况下是否返回友好提示

### 7. 可选：前端工具元数据

MCP 工具的前端展示元数据（图标、标签、排序）由后端 `GET /api/tools` 接口提供（`ToolMeta` 在 `composables/toolMetadata.ts` 中缓存）。
无需前端手动注册——只要后端 `ToolDefinition` 和 `Tool` 类的 `icon` / `label` / `order` 属性正确设置即可。

如需额外的前端展示逻辑（如调用/结果文本格式化），在 `composables/toolMetadata.ts` 中追加条目。

## 示例

### 示例 1：封装 GitHub API

```
用户: "把 GitHub 封装成工具"

→ 1. 分析：GitHub REST API，6 个工具（搜索仓库、仓库详情、读取文件、搜索代码、Issue 列表、PR 列表）
→ 2. 编写 ToolDefinition：每个工具含中文描述、enum 约束、默认值
→ 3. 实现 github_server.py：FastAPI + TOOL_REGISTRY + /tools/list + /tools/call
→ 4. 本地测试：curl 验证工具发现和调用
→ 5. 注册：PUT /api/mcp/config，JSON 配置中引用启动的服务器地址
→ 6. 验证：对话 "搜索 GitHub 上 star 最多的 FastAPI 项目"
```

### 示例 2：封装天气 API

```
用户: "我想让 AI 能查天气，封装成工具"

→ 1. 分析：天气 API (api.weatherapi.com)，1 个工具（查当前天气）
   参数：city (required), country (optional)
→ 2. ToolDefinition：
   - name: "weather_current"
   - description: "查询指定城市的当前天气。返回温度、湿度、风速、天气状况。需要 WEATHER_API_KEY 环境变量。"
   - parameters: {city: {type: string, required}, country: {type: string, default: ""}}
→ 3. 创建 backend/mcp_servers/weather_server.py，参考上方骨架模板
→ 4. 本地测试 + 类型检查
→ 5. 注册到 IrisFlow
→ 6. 对话测试："北京今天天气怎么样？"
```
