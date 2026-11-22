# CLAUDE.md

IrisFlow v0.38.1 — LLM Chat + Agent 控制台。后端 FastAPI + OpenAI-compatible 网关，前端 Vite + Vue 3。

## 命令

```bash
# 后端
cd backend && uv sync
uv run uvicorn main:app --reload --timeout-graceful-shutdown 3
uv run pyright --project pyrightconfig.json   # 类型检查

# 前端
cd frontend && pnpm install
pnpm dev                          # http://localhost:3000
npx vue-tsc --noEmit             # 类型检查
```

## 核心概念

**会话 (Session)** vs **对话 (Message Round)**：会话是整个聊天记录容器，对话是会话内的单轮用户↔LLM 交互。

会话四色状态：🟢 completed → 🟡 generating → 🔵 pending（队列等待）。所有异常回到 completed。

后端是状态的唯一权威源。客户端订阅 `GET /api/sessions/status-stream` 获取实时状态推送，`GET /api/conversations` 获取列表元数据（不含状态）。

## 关键设计

- **config.py** — `AppConfig` 单例，配置从 `data/*.json` 加载，无 `.env`。`${VAR}` 密钥替换。
- **agent.py + router.py** — 工具调用**双循环**：内置工具在 `router._generate` 流式循环（`while True`）自动执行并回传；自定义工具经 SSE 暂停 → `POST /api/agent/chat/continue` → `continue_with_results()` 续跑（最多 10 轮，自动循环无迭代计数）。
- **llm/tools/** — `ToolExecutor` 单例，`Tool` 抽象基类 + 每工具独立模块。MCP 工具通过 `register()` 动态注入。
- **mcp.py** — `MCPManager` 单例，标准 MCP 协议（JSON-RPC 2.0 over stdio/HTTP），运行时增删 + 文件监听热重载。
- **client.py** — OpenAI-compatible API 封装，流式 SSE 事件（reasoning/content/tool_calls）。
- **context.py** — 上下文压缩：超预算时截断长工具结果 + 丢弃最老轮次，仅作用于请求副本。
- **sessions.py** — `SessionStore`：SQLite 持久化 + LRU（100）+ TTL（1h），`asyncio.Lock` 守护。
- **router.py** — 统一 FIFO 队列 + LLM 健康门控 + 并发控制，`asyncio.shield()` 保护 cleanup。
- **composer/** — 视频合成器域包：`store.py`（SQLite 三表 + 项目/渲染 CRUD + 引用计数）、`assets.py`（下载 + hash 去重 + MIME 判型 + ffprobe 探测）、`timeline.py`（时间轴校验 + SRT/ASS）、`tts.py`（三级降级 + 长文本分句 + 多说话人）、`music.py`（Stable Audio sidecar）、`ffmpeg.py`（探测 + 分段渲染/xfade/Ken Burns/ASS/侧链混音命令 + 进度解析）、`queue.py`（渲染队列 + 状态机 + 取消/优雅关闭）、`maintenance.py`（磁盘 LRU 回收）、`router.py`（`/api/composer/*` REST + SSE）。`data/composer/` 为存储根；本地模型 sidecar 见 `deploy/`（端口 9701/9702）。
- **constants.py / constants.ts** — 前后端共享常量，无硬编码字符串。

## 前端架构

- **API** — `api/client.ts`：fetch 封装 + SSE 流式解析 + 可配置后端地址。
- **useAgent** — 统一 chat/agent 状态管理，每会话独立状态 Map。
- **toolMetadata** — 工具元数据模块级单例，`discoverTools()` 从后端拉取。
- **useComposer** — 合成器前端状态模块级单例：素材 / 项目 / 渲染 + SSE 订阅（断线重连），多浮窗共享。
- **TimelineTracks** — 轨道式时间轴：时间标尺、播放头素材预览、视频块拖拽重排。
- **FloatingWindow** — 通用浮窗框架：Teleport、拖拽、置顶、z-index 分层管理。
- **Markdown** — markdown-it + KaTeX + highlight.js。

## 开发流程

- **PLAN.md** — 视频合成器（IRIS VIDEO COMPOSER）的唯一规划源：M1-M5 全部完成（0.38.0，GA），含数据模型、API 表、ffmpeg 分段渲染管线、TTS/BGM provider 设计。
- **工作流**：里程碑开工前将任务写入 `CHANGELOG.md` 待发布区作为开发指令 → `/implementation` 实施 → `/version-bump` 收尾（版本号 + README + CHANGELOG 转正）。版本号单一来源：`backend/pyproject.toml`。
