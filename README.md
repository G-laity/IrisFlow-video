# IrisFlow

[![License](https://img.shields.io/badge/许可证-Apache_2.0-blue)]()
[![Status](https://img.shields.io/badge/状态-GA-brightgreen)]()
[![Version](https://img.shields.io/badge/版本-0.41.0-green)]()
[![Python](https://img.shields.io/badge/Python-3.14-blue)]()

**IrisFlow** 是一个 LLM Chat + Agent 控制台。后端基于 FastAPI 提供 OpenAI-compatible 网关，前端基于 Vite + Vue 3 提供聊天面板。支持流式对话（SSE）、Agent 工具调用推理循环、MCP 外部工具集成（浏览器自动化 / GitHub / 图像视频生成）、会话持久化与多格式文件上传。

## ✨ 功能特性

### 对话与推理

| 功能 | 说明 |
|------|------|
| 💬 流式聊天 | SSE 实时推送 `reasoning` / `content` / `tool_call` / `tool_result` 事件，心跳保活，页面刷新后可从事件历史续传 |
| 🧠 思考模式 | 每轮对话独立开关，思考过程流式展示；兼容 DeepSeek 等模型的 `reasoning_content` 多轮回传校验 |
| 🤖 Agent 工具循环 | 多轮工具调用推理：内置工具自动执行并循环回传直至模型给出最终回复；自定义工具暂停等待手动执行后继续（最多 10 轮迭代） |
| 📐 上下文压缩 | 对话超出预算时自动压缩：长工具结果截断保留首尾 → 按轮丢弃最老对话（保持工具调用配对）→ 注入压缩提示；仅作用于请求副本，历史完整保留 |
| 🗑️ 生成中止 | 随时终止正在生成/排队中的回复，会话状态自动恢复 |

### 工具生态

| 工具 | 来源 | 能力 |
|------|------|------|
| `web_search` | 内置 | DuckDuckGo 网页搜索（Instant Answer + HTML 回退） |
| `open_url` | 内置 | trafilatura 智能网页内容提取 |
| `calculator` | 内置 | 安全表达式计算（白名单函数） |
| `browser_*`（25 个） | MCP · Playwright | 浏览器自动化：导航、点击、输入、截图、页面快照、JS 执行、网络监控 |
| `github`（40+ 个） | MCP · GitHub Copilot | 仓库管理、代码搜索、Issue/PR 操作、评审评论 |
| `agnes_*`（3 个） | MCP · Agnes AI | **图像生成**、**视频生成**（文生视频 + 状态查询） |

工具通过标准 MCP 协议（JSON-RPC 2.0 over stdio/HTTP）动态注入，运行时增删服务器自动重连，配置文件变更热重载。

### 会话与数据

| 功能 | 说明 |
|------|------|
| 💾 会话持久化 | SQLite 存储，LRU（100 上限）+ TTL（1 小时闲置），重启后完整恢复 |
| 🚦 会话状态 | 四色状态灯（🟢 completed / 🟡 generating / 🔵 pending），SSE 实时推送，多标签页同步 |
| 📎 文件上传 | 90+ 文件类型（最大 10 MB）：图片转 base64 多模态、文本直读、文档经 MarkItDown 转 Markdown |
| 📺 媒体预览 | 图片 / 视频 / 网页 / 文件的统一预览浮窗 |
| 📝 Markdown 渲染 | markdown-it + KaTeX 数学公式 + highlight.js 代码高亮 |

### 控制台界面

| 功能 | 说明 |
|------|------|
| 🪟 浮窗框架 | 通用 FloatingWindow：拖拽、置顶、视口约束、z-index 分层管理；浮岛按钮以流体形态展开 |
| 🧊 卡片玻璃 | 三级玻璃（Blur / Tint / 实色回退）+ 四点掠射 + 1px 边缘色散 + 指针驱动折射 |
| 📋 会话列表 | 按日期分组、置顶、重命名、删除、状态灯 |
| 🔍 工作流日志 | Agent 推理步骤时间线（思考 → 工具调用 → 结果），工具结果 JSON 高亮 |
| ⚙️ 设置面板 | 标签页式：服务器 / LLM / MCP / 密钥 / 默认参数 / 关于，全量配置持久化到 JSON 文件（无 `.env`，`${VAR}` 密钥引用） |
| 🎚️ 会话参数 | 预设胶囊 + 基础/高级标签页：temperature、max_tokens、top_p、top_k、惩罚系数、系统提示词 |

## 🛠️ 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| **前端** | Vite + Vue 3 + TypeScript | Agent 控制台，无 SSR |
| **后端框架** | FastAPI (Python 3.14) | RESTful API + SSE |
| **包管理** | uv (Python) / pnpm (Node.js) | 依赖与项目管理 |
| **LLM 网关** | OpenAI-compatible API | Chat + Agent 推理（流式 / 思考 / 工具调用） |
| **工具引擎** | 内置工具 + MCP | DuckDuckGo / trafilatura / Playwright / GitHub / Agnes AI |
| **会话持久化** | SQLite | 会话上下文重启后自动恢复 |
| **Markdown** | markdown-it + KaTeX + highlight.js | 公式渲染 + 代码高亮 |

## 🚀 快速开始

### 环境要求

| 工具 | 版本 | 用途 |
|------|------|------|
| [Python](https://www.python.org/downloads/) | **3.14** | 后端运行时 |
| [uv](https://docs.astral.sh/uv/) | 最新版 | Python 包管理 |
| [Node.js](https://nodejs.org/) | **24** | 前端运行时 |
| [pnpm](https://pnpm.io/installation) | 最新版 | Node 包管理 |
| [Git](https://git-scm.com/) | 最新版 | 版本控制 |
| [ffmpeg](https://ffmpeg.org/download.html)（可选） | 任意较新版本 | 视频合成器素材探测与渲染 |

### 1. 克隆仓库

```bash
git clone https://github.com/Laity999/IrisFlow-video.git
cd IrisFlow-video
```

### 2. 启动后端

```bash
cd backend
uv sync                                        # 安装依赖
uv run fastapi dev main.py                     # 启动开发服务器
```

> Windows 用户如遇到编码错误，请在命令前加上 `PYTHONUTF8=1`：
> ```bash
> PYTHONUTF8=1 uv run fastapi dev main.py
> ```

后端 API 运行在 `http://localhost:8000`，可通过 `http://localhost:8000/docs` 查看自动生成的 Swagger 文档。

### 3. 启动前端

另开一个终端：

```bash
cd frontend
pnpm install                                   # 安装依赖
pnpm dev                                       # 启动开发服务器
```

打开浏览器访问 `http://localhost:3000` 即可看到控制台页面。

### 4. 安装 ffmpeg（视频合成器可选）

合成器素材库的元数据探测与后续渲染依赖 ffmpeg / ffprobe。启动时自动探测（配置路径 → 系统 `PATH`），缺失不阻塞启动，合成器面板会显示提示。

```bash
# Windows（winget）
winget install Gyan.FFmpeg

# Windows（官网下载，解压后需自行加入 PATH，或在合成器设置中配置路径）
#   https://ffmpeg.org/download.html

# Linux（Debian / Ubuntu）
sudo apt install ffmpeg
```

### 5. 本地模型 sidecar（视频合成器可选）

旁白与 BGM 生成可选用本地模型（CosyVoice / Stable Audio），以独立进程运行。
需要 NVIDIA GPU（两个模型均走 GPU 推理；RTX 50 系需驱动支持 **CUDA 12.8+**，显存各约 2-3 GB）：

```powershell
# 首次安装（含国内源与 Windows 兼容补丁，详见 deploy/README.md）
pushd deploy\cosyvoice;    .\setup.ps1; popd
pushd deploy\stable-audio; .\setup.ps1; popd

# 启动服务（各开一个终端）
cd deploy\cosyvoice;    .\serve.ps1    # 语音，端口 9701
cd deploy\stable-audio; .\serve.ps1    # 背景音乐，端口 9702
```

启动后可用 `curl http://127.0.0.1:9701/health` 与 `curl http://127.0.0.1:9702/health` 验证；
模型在收到首个合成请求时加载（CosyVoice 约 10s、Stable Audio 约 80s）。

**不部署也能工作**——语音自动降级到 edge-tts（免费、需联网），音乐可上传现成 BGM。
完整部署说明见 [`deploy/README.md`](./deploy/README.md)。

### 6. 初始配置

首次使用需在控制台 **设置面板** 中配置：

1. **LLM**：网关地址（如 `https://api.deepseek.com`）、模型 ID（如 `deepseek-flash`）、鉴权 Token（支持 `${VAR}` 引用密钥）
2. **密钥**：将 Token 等敏感值存入密钥库，配置中以 `${VAR_NAME}` 引用
3. **MCP**（可选）：配置 `mcp.json` 接入 Playwright / GitHub / Agnes AI 等工具服务器

### 验证安装

```bash
# 测试后端根接口
curl http://localhost:8000/
# → {"name":"IrisFlow","version":"0.41.0",...}

# 测试健康检查
curl http://localhost:8000/api/health
# → {"status":"healthy","base_url":"...","default_model":"..."}
```

## 📡 API 一览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` `/version` `/status` `/api/ping` | GET | 系统信息 / 版本 / 运行状态 / 心跳 |
| `/api/health` | GET | LLM 网关连通性探测 |
| `/api/conversations` | GET / POST | 会话列表 / 新建会话 |
| `/api/conversations/{id}` | GET / PATCH / DELETE | 会话详情 / 改名置顶 / 删除 |
| `/api/conversations/{id}/messages/stream` | POST | 发送消息（SSE 流式，支持 thinking + 工具） |
| `/api/conversations/{id}/stream` | GET | 重连进行中的生成流（页面刷新续传） |
| `/api/conversations/{id}/abort` | POST | 中止生成 |
| `/api/sessions/status-stream` | GET | 会话状态实时订阅（SSE） |
| `/api/agent/chat/continue` | POST | 回传自定义工具执行结果，继续推理 |
| `/api/upload` `/api/upload/config` | POST / GET | 文件上传 / 支持类型与限制 |
| `/api/tools` | GET | 工具元数据（图标 / 标签 / 排序 / 描述）+ 工具组 |
| `/api/mcp/config` `/api/mcp/status` | GET / PUT · GET | MCP 配置读写 / 服务器连接状态 |
| `/api/llm/config` `/api/llm/concurrency` | GET / PUT · GET | LLM 配置 / 并发上限 |
| `/api/session-settings/default` | GET / PUT | 会话默认采样参数 |
| `/api/secrets` | GET / PUT | 密钥库（值不回传，仅 key 列表） |
| `/api/composer/assets` | GET / POST | 素材列表（kind 过滤）/ URL 导入（hash 去重 + ffprobe 探测） |
| `/api/composer/assets/upload` | POST | 素材上传（500 MB 上限，仅媒体类型） |
| `/api/composer/assets/tts` | POST | 语音合成入库（CosyVoice → 云端 → edge-tts 三级降级） |
| `/api/composer/assets/music` | POST | BGM 生成入库（Stable Audio sidecar） |
| `/api/composer/assets/{id}` | GET / DELETE | 素材详情（探测元数据）/ 删除（引用计数校验） |
| `/api/composer/assets/{id}/file` | GET | 素材流式播放（支持 HTTP Range） |
| `/api/composer/projects` | GET / POST | 项目列表 / 创建（可携带脚本） |
| `/api/composer/projects/{id}` | GET / PATCH / DELETE | 项目详情 / 更新（时间轴走 Schema 校验）/ 删除 |
| `/api/composer/projects/{id}/srt` | GET | 下载时间轴字幕 SRT |
| `/api/composer/projects/{id}/render` | POST | 提交渲染（异步队列，返回 render_id） |
| `/api/composer/renders` | GET | 渲染任务列表（project_id 过滤） |
| `/api/composer/renders/{id}` | GET | 渲染详情（状态 + 实时进度 + 错误） |
| `/api/composer/renders/{id}/cancel` | POST | 取消渲染（杀 ffmpeg 子进程） |
| `/api/composer/renders/{id}/file` | GET | 成品 MP4 流式播放（Range）/ `?download=1` 下载 |
| `/api/composer/status-stream` | GET | 合成器事件流（SSE：素材 / 项目变更） |
| `/api/composer/config` | GET / PUT | 合成器配置 + ffmpeg / TTS / 音乐 provider 探测 |
| `/api/composer/templates` | GET | 项目模板（产品介绍 / 口播 / 图文混排） |
| `/api/composer/maintenance/usage` | GET | 磁盘占用快照（上限 / 目标水位 / 自动清理开关） |
| `/api/composer/maintenance/cleanup` | POST | 手动执行磁盘 LRU 回收（未引用素材 → 旧渲染产物） |

## 📂 项目结构

```
IrisFlow/
├── backend/
│   ├── main.py                  # 入口，挂载路由 + lifespan（MCP 自动连接 + 残留状态清理）
│   ├── core/                    # config.py（配置单例 + JSON 持久化） / info.py（系统信息端点）
│   ├── llm/                     # IRIS LLM — Chat + Agent + Tools + MCP
│   │   ├── client.py             #   LLM 网关客户端（OpenAI-compatible，流式 + 工具调用累积 + 健康探测）
│   │   ├── context.py            #   上下文压缩（工具结果截断 + 轮次丢弃，仅作用于请求副本）
│   │   ├── chat.py               #   Chat 类 — 消息历史容器
│   │   ├── agent.py              #   Agent(Chat) — 工具调用推理循环（自定义工具暂停/继续）
│   │   ├── tools/                  #   工具包（注册表 + 执行器 + 每工具独立模块）
│   │   │   ├── __init__.py         #     ToolExecutor 单例 + BUILTIN_TOOLS 注册
│   │   │   ├── base.py             #     Tool 抽象基类
│   │   │   ├── web_search.py       #     网页搜索工具
│   │   │   ├── calculator.py       #     计算辅助工具
│   │   │   ├── open_url.py         #     打开网页工具
│   │   │   └── composer.py         #     合成器八工具（项目 / 导入 / TTS / BGM / 时间轴 / 渲染占位）
│   │   ├── mcp.py                #   MCP 管理器 — JSON-RPC 2.0 over stdio/HTTP，动态注入 + 热重载
│   │   ├── sessions.py           #   SessionStore — LRU + TTL + SQLite 持久化
│   │   ├── uploads.py            #   文件上传（图片多模态 / MarkItDown 文档转换）
│   │   ├── constants.py          #   全模块共享常量（会话状态、消息角色、SSE 事件类型）
│   │   ├── models.py             #   Pydantic 模型（Chat/Agent/Tool/会话）
│   │   └── router.py             #   REST 路由 + 统一队列调度 + LLM 健康门控
│   ├── composer/                 # IRIS VIDEO COMPOSER — 视频合成器域包
│   │   ├── config.py             #   合成器配置（composer_config.json + 预设 + TTS/音乐段）
│   │   ├── store.py              #   ComposerStore — SQLite 三表（projects/assets/renders）
│   │   ├── assets.py             #   素材服务 — URL 下载 + hash 去重 + MIME 判型 + ffprobe 探测
│   │   ├── timeline.py           #   时间轴 Schema 校验 + SRT 生成 + 引用提取
│   │   ├── tts.py                #   语音合成（三级降级链 + 长文本分句 + 多说话人对话）
│   │   ├── music.py              #   背景音乐生成（Stable Audio sidecar）
│   │   ├── maintenance.py        #   磁盘占用快照 + LRU 回收（未引用素材 / 旧渲染）
│   │   ├── ffmpeg.py             #   ffmpeg 探测 + 分段渲染 / xfade / Ken Burns / ASS 字幕 / 混音命令 + 进度解析
│   │   ├── queue.py              #   渲染队列：FIFO + worker + 状态机 + 取消 / 优雅关闭
│   │   └── router.py             #   REST + SSE 路由（素材 / 项目 / 渲染 / 配置 / 状态流）
│   ├── data/                     # 配置 JSON + SQLite 数据库（sessions.db）
│   ├── pyproject.toml
│   └── pyrightconfig.json
├── frontend/                    # 前端（Vite + Vue 3）
│   ├── src/
│   │   ├── App.vue               #   根组件 — 会话列表 + 聊天面板 + 动态浮窗 + 心跳
│   │   ├── api/client.ts         #   fetch 封装 + SSE 流式 + 可配置后端地址
│   │   ├── constants.ts          #   全模块共享常量
│   │   ├── composables/          #   useAgent + drafts + toolMetadata + useComposer + useTheme + useTabIndicator + windowZIndex + useGlassPointer
│   │   ├── utils/                #   纯函数 + Markdown 渲染（懒加载）+ 工具调用文本清洗 + 媒体类型判定 + fluidMorph 弹簧关键帧
│   │   └── components/           #   Vue SFC 组件
│   │       ├── floating/          #     浮窗子窗体（全部基于 FloatingWindow 框架）
│   │       │   ├── FloatingWindow.vue    #     通用浮窗框架 — 可拖拽 + 置顶 + 视口约束
│   │       │   ├── ConversationList.vue  #     会话列表 — 分组 + 置顶 + 重命名 + 删除 + 状态灯 + SSE 订阅
│   │       │   ├── SettingsPanel.vue     #     设置面板 — 服务器/LLM/MCP/密钥/默认参数/关于 + 全量配置持久化
│   │       │   ├── ToolGroupPanel.vue    #     工具管理浮窗 — MCP 服务器工具组开关
│   │       │   ├── WorkflowDetail.vue    #     工作流详情 — 工具调用 / 结果 / 思考过程查看
│   │       │   ├── ComposerPanel.vue     #     合成器主浮窗 — 素材库标签页（M1）+ 项目/时间轴/渲染占位
│   │       │   └── MediaPreview.vue      #     统一媒体预览 — 图片/视频/网页 + 文件 Markdown 渲染
│   │       ├── composer/         #     合成器子组件
│   │       │   ├── AssetLibrary.vue      #     素材库 — 网格 + 过滤 + 上传/导入 + TTS/BGM 快捷生成
│   │       │   ├── ProjectList.vue       #     项目列表 — 新建（标题 + 脚本）+ 选择 + 删除
│   │       │   ├── StoryboardEditor.vue  #     分镜编辑器 — 镜头卡片 + 字幕列表 + 旁白/BGM 轨（PATCH 即存）
│   │       │   ├── RenderQueue.vue       #     渲染队列 — 进度条 + 状态灯 + 取消 + 成品预览/下载
│   │       │   └── TimelineTracks.vue    #     轨道式时间轴 — 标尺 + 播放头预览 + 拖拽重排
│   │       ├── ChatPanel.vue      #     聊天面板 — 消息滚动 + 会话加载
│   │       ├── ChatInput.vue      #     输入框 — 工具切换 + 思考开关 + 文件上传
│   │       ├── MessageBubble.vue  #     消息气泡 — Markdown 渲染 + 思考过程
│   │       ├── SessionSettingsPanel.vue  #  会话参数面板 — 预设胶囊 + 基础/高级标签页
│   │       ├── WorkflowLog.vue    #     工作流日志 — Agent 推理步骤时间线
│   │       └── ImageViewer.vue    #     图片缩略图组件
│   └── vite.config.ts            #   Vite 配置 + /api 反向代理
└── README.md
```

## 🏗️ 架构

IrisFlow 采用前后端分离设计。后端是状态的唯一权威源：统一 FIFO 队列调度 + LLM 健康门控 + 并发控制；客户端通过 SSE 订阅实时状态。

```mermaid
graph TD
    subgraph 前端
        CONSOLE[前端控制台\nVite + Vue 3]
    end
    subgraph "后端"
        ROUTER[router.py\n统一队列 + 健康门控]
        AGENT[agent.py\nAgent 工具调用循环]
        CONTEXT[context.py\n上下文压缩]
        CLIENT[client.py\nLLM 网关客户端]
        TOOLS[ToolExecutor\n工具执行器]
        MCP[MCPManager\n外部工具注入]
        SESSIONS[SessionStore\nSQLite 持久化]
    end
    subgraph "外部"
        GATEWAY[LLM 网关\nDeepSeek / OpenAI 等]
        WEB[互联网\nDuckDuckGo / trafilatura]
        MCP_SRV[MCP 服务器\nPlaywright / GitHub / Agnes]
    end
    CONSOLE -->|REST + SSE| ROUTER
    ROUTER -->|调度生成任务| AGENT
    AGENT -->|"① 每轮迭代：压缩请求副本"| CONTEXT
    CONTEXT --> CLIENT
    CLIENT <-->|"流式 reasoning / content / tool_calls"| GATEWAY
    CLIENT -->|tool_calls 事件| AGENT
    AGENT -->|"② 发起工具调用"| TOOLS
    TOOLS -->|内置工具| WEB
    TOOLS -->|"③ 执行结果回传 → 回到 ① 进入下一轮"| AGENT
    TOOLS -.->|"自定义工具：SSE 下发，暂停等待"| CONSOLE
    CONSOLE -.->|"手动执行结果回传"| ROUTER
    MCP -->|工具注册| TOOLS
    MCP -->|JSON-RPC| MCP_SRV
    ROUTER <-->|持久化| SESSIONS
```

图中 ① → ② → ③ 构成 Agent 的**工具调用循环**：每轮迭代先压缩请求副本，再流式调用 LLM；模型发起工具调用时执行并将结果回传，进入下一轮，直至模型给出最终回复。自定义 / MCP 工具（虚线）暂停等待前端手动执行，经 `/api/agent/chat/continue` 续跑推理。

### 后端核心模块

- **Chat**（`llm/chat.py`）— 消息历史容器，会话采样参数（temperature / max_tokens / top_p / top_k / 惩罚系数）随消息更新。
- **Agent**（`llm/agent.py`）— 继承 Chat，工具调用推理循环。内置工具在 `router._generate` 的流式循环中自动执行并回传；自定义工具暂停等待前端手动执行，经 `continue_with_results()` 续跑（最多 10 轮）。
- **Tools**（`llm/tools/`）— `ToolExecutor` 单例管理注册与执行（超时守护、错误隔离）。内置 `web_search` / `open_url` / `calculator`，MCP 工具经 `register()` 动态注入。
- **MCP**（`llm/mcp.py`）— `MCPManager` 单例，标准 MCP 协议（JSON-RPC 2.0 over stdio/HTTP）。启动 diff 重连、运行时增删、文件监听热重载、进程健康检查。
- **Client**（`llm/client.py`）— OpenAI-compatible API 封装。`chat_stream_events()` 产出带类型 SSE 事件（`reasoning` / `content` / `tool_calls`），流式工具调用增量累积；思考模式兼容 `reasoning_content` 多轮回传；400/5xx 错误记录响应体详情。
- **Context**（`llm/context.py`）— 上下文压缩：超长工具结果截断 + 按轮丢弃最老对话 + 压缩提示注入，token 启发式估算。
- **Sessions**（`llm/sessions.py`）— `SessionStore`：SQLite 持久化 + LRU（100）+ TTL（1h），`asyncio.Lock` 守护。
- **Router**（`llm/router.py`）— 统一 FIFO 队列 + LLM 健康门控 + 并发控制，`asyncio.shield()` 保护清理。

### 前端

- **API**（`api/client.ts`）— fetch 封装 + SSE 流式解析 + 可配置后端地址。
- **useAgent** — 统一 chat/agent 状态管理，每会话独立状态 Map；页面刷新后从后端事件历史续传。
- **toolMetadata** — 工具元数据模块级单例，`discoverTools()` 从后端拉取，无硬编码。
- **FloatingWindow** — 通用浮窗框架：Teleport、拖拽、置顶、z-index 分层管理。
- **Markdown** — markdown-it + KaTeX + highlight.js。

## 🔄 工作流

1. 用户在控制台输入消息，可选择启用工具组与思考模式。
2. 消息经 SSE 流式发送到后端，LLM 实时返回 reasoning 和 content。
3. 模型发起工具调用时：内置工具自动执行并将结果回传 LLM 继续推理；自定义工具暂停等待用户手动执行。
4. 前端实时展示工作流日志（思考 → 工具调用 → 结果 → 最终回复）。
5. 对话超出上下文预算时自动压缩（工具结果截断 + 旧轮丢弃），历史完整保留。
6. 会话自动保存到 SQLite，重启后完整恢复。

## 🗺️ 下一步计划

### 🎬 视频合成器（IRIS VIDEO COMPOSER）

将 IrisFlow 生成的各类媒体素材整合为完整视频（规划详见 [PLAN.md](./PLAN.md)）：

- ✅ **M1 · 素材管线（0.34.0）**：素材库落地——URL 导入 / 本地上传（500 MB、仅媒体类型）、sha256 去重、ffprobe 元数据探测、hash 分桶存储、引用计数删除、合成器浮窗（网格缩略图 + 类型过滤）、SSE 实时推送、ffmpeg 启动探测与可配置路径
- ✅ **M2 · 时间轴 + 编排 + 语音/音乐生成（0.35.0）**：时间轴 Schema 校验 + SRT 生成、项目 CRUD 与引用计数、Agent 八工具集（项目 / 素材导入 / Agnes 轮询入库 / TTS / BGM / 时间轴 / 渲染占位）、TTS 三级降级（CosyVoice sidecar → 云端 → edge-tts）、Stable Audio BGM、分镜编辑器（镜头 / 字幕 / 旁白 / BGM，PATCH 即存）、素材页 TTS/BGM 快捷生成、本地模型 sidecar 部署脚本（deploy/）
- ✅ **M3 · 渲染 MVP（0.36.0）**：分段渲染 + concat 拼接 + SRT 字幕烧录 + 旁白/BGM 混音、渲染队列与状态机、SSE 实时进度、取消（杀进程）、成品 MP4 预览/下载、磁盘水位告警、重启中断恢复
- ✅ **M4 · 高级合成（0.37.0）**：xfade 转场（fade / dissolve / slide）、Ken Burns 运镜（zoom + pan）、ASS 样式字幕（默认 / 大字 / 顶部 / 简约）、旁白侧链压 BGM、TTS 长文本自动分句与多说话人对话、编码参数可配置（preset / crf / 码率）
- ✅ **M5 · 体验完善（0.38.0，GA）**：轨道式时间轴（标尺 / 播放头预览 / 拖拽重排）、项目模板（产品介绍 / 口播 / 图文混排）、磁盘 LRU 回收（手动 + 水位自动）、对话工具结果「发送到合成器」、渲染完成 toast

> 🎉 **IRIS VIDEO COMPOSER 五个里程碑（M1-M5）全部完成，特性标记 GA（0.38.0）**。

## 📄 许可证

本项目基于 Apache-2.0 开源。
