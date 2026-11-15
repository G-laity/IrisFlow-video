# IrisFlow 后端

LLM Chat + Agent 控制台后端，FastAPI + OpenAI-compatible 网关。

## 快速开始

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run fastapi dev main.py
# Windows: PYTHONUTF8=1 uv run fastapi dev main.py
```

进入前端设置面板（`http://localhost:3000` → 齿轮图标）配置 LLM 网关地址等信息。

## 模块

- **core** — 应用配置（JSON 持久化）、系统信息、生命周期管理
- **llm** — LLM 调用（Chat / Agent）、工具引擎、MCP 集成、会话管理
