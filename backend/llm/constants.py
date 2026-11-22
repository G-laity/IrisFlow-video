"""LLM 模块常量 —— 全模块共享的字符串、枚举值、配置键。

所有硬编码字符串集中于此，方便维护与搜索。
"""

# ── 会话 ──────────────────────────────────────────────

DEFAULT_TITLE = "无标题"
MODE_CHAT = "chat"
MODE_AGENT = "agent"

# ── 会话状态 ──────────────────────────────────────────

STATUS_GENERATING = "generating"
STATUS_COMPLETED = "completed"
STATUS_PENDING = "pending"
STATUS_UNKNOWN = "unknown"
STATUS_REPLACED = "replaced"  # SSE 订阅替换哨兵

# ── 消息状态（每轮 assistant 对话的终止状态）─────────────

MSG_QUEUED = "queued"
MSG_GENERATING = "generating"
MSG_COMPLETED = "completed"
MSG_ABORTED = "aborted"

# ── 消息角色 ──────────────────────────────────────────

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"
ROLE_TOOL = "tool"

# ── SSE 事件类型 ──────────────────────────────────────

SSE_REASONING = "reasoning"
SSE_CONTENT = "content"
SSE_TOOL_CALLS = "tool_calls"
SSE_TOOL_CALL = "tool_call"
SSE_TOOL_RESULT = "tool_result"
SSE_SESSION = "session"
SSE_TITLE = "title"
SSE_ERROR = "error"
SSE_STATUS = "status"
SSE_DONE = "[DONE]"

# ── 系统提示词 ──────────────────────────────────────────

SYSTEM_PROMPT = (
    "主动使用工具获取和验证信息，可以循环使用，直至确定为止。"
    "不要编造不确定的内容，引用信息时说明来源。"
)

# ── LLM 客户端（client.py）───────────────────────────────

LLM_TIMEOUT = 120.0           # 非流式 / 流式 API 调用超时（秒）
HEALTH_CHECK_TIMEOUT = 30.0   # 健康检查超时（秒）
LLM_PING_TIMEOUT = 5.0        # 轻量 ping 超时（秒）
SSE_DATA_PREFIX = "data: "    # SSE 行前缀
API_MODELS_PATH = "/models"
API_CHAT_PATH = "/chat/completions"
HEALTH_PING_TEXT = "ping"     # 健康检查测试消息
HEALTH_PING_MAX_TOKENS = 1    # 健康检查 token 限制
ERROR_DETAIL_TRUNCATE = 500   # HTTP 错误详情截断长度
ERROR_RESULT_TRUNCATE = 300   # 健康检查结果截断长度
REASONING_EFFORT_NONE = "none"
THINKING_ENABLED_TYPE = "enabled"

# ── 上下文压缩（context.py）─────────────────────────────────

CONTEXT_WINDOW_TOKENS = 96 * 1024   # 上下文窗口估算上限（token），超预算时压缩
CONTEXT_OUTPUT_RESERVE = 8192       # 未设置 max_tokens 时为输出预留的 token
TOOL_RESULT_MAX_CHARS = 6000        # 工具结果超过此长度时截断保留首尾（字符）
TOOL_RESULT_HEAD_CHARS = 3000       # 截断保留的头部长度
TOOL_RESULT_TAIL_CHARS = 3000       # 截断保留的尾部长度
CONTEXT_COMPRESS_NOTICE = (
    "【系统提示】对话历史过长，更早的 {dropped} 轮对话已省略。"
    "请基于当前可见的上下文继续；如需更早的信息，请向用户询问。"
)

# ── 路由与调度（router.py）─────────────────────────────────

CLEANUP_DELAY = 300.0         # 生成状态清理延迟（秒，给页面刷新留重连窗口）
LLM_RECOVERY_POLL_INTERVAL = 5  # LLM 恢复轮询间隔（秒）
SHUTDOWN_TASK_WAIT = 3.0       # 优雅关闭等待 Task 超时（秒）
TITLE_MAX_LENGTH = 40          # 自动标题最大字符数
TITLE_CHAR_WINDOW = 1200       # 标题生成对话截断窗口（字符）
TITLE_MESSAGE_WINDOW = 20      # 标题生成最近消息条数
TITLE_MODEL_TEMP = 0.2         # 标题生成模型温度
TITLE_MODEL_MAX_TOKENS = 200   # 标题生成最大 token
SSE_MEDIA_TYPE = "text/event-stream"  # SSE 响应 Content-Type
SSE_HEARTBEAT_INTERVAL = 15.0         # SSE 心跳间隔（秒）—— 工具执行期间无数据时发送注释保活
MCP_RELOAD_TIMEOUT = 30.0           # MCP 配置重载超时（秒）
MCP_HEALTH_CHECK_INTERVAL = 30.0     # MCP 进程健康检查间隔（秒）
MCP_FILE_WATCH_INTERVAL = 3.0       # MCP 配置文件变更检测间隔（秒，远小于健康检查周期）
MCP_SSE_TRUNCATE = 200               # MCP SSE 日志截断长度
MCP_STDERR_BUFFER = 50               # MCP stderr 缓冲区行数上限
SQLITE_BUSY_TIMEOUT = 2000           # SQLite 忙等待超时（ms）

# ── 默认会话设定 ────────────────────────────────────────

DEFAULT_SESSION_SETTINGS: dict[str, object] = {
    "system_prompt": None,
    "temperature": None,
    "max_tokens": None,
    "top_p": None,
    "top_k": None,
    "presence_penalty": None,
    "frequency_penalty": None,
    "repeat_penalty": None,
}

# ── 会话存储（sessions.py）────────────────────────────────

SESSION_ID_LENGTH = 12          # session_id 字符长度

# ── 工具（tools/ 包）──────────────────────────────────────

WEB_SEARCH_TIMEOUT = 8.0        # 网页搜索 HTTP 超时（秒）—— 网络请求 ≤10s
WEB_SEARCH_DEFAULT_COUNT = 5    # 默认搜索结果数
WEB_SEARCH_MAX_COUNT = 10       # 最大搜索结果数
WEB_SEARCH_HTML_FALLBACK = 3    # 回退到 HTML 搜索的阈值
WEB_SEARCH_RETRIES = 1          # 搜索失败重试次数
WEB_SEARCH_RETRY_DELAY = 0.5    # 搜索重试间隔（秒）
OPEN_URL_TIMEOUT = 8.0          # 打开网页 HTTP 超时（秒）—— 网络请求 ≤10s
OPEN_URL_RETRIES = 1            # 打开网页重试次数
OPEN_URL_RETRY_DELAY = 0.5      # 打开网页重试间隔（秒）
OPEN_URL_TRUNCATE = 4000        # 网页内容截断长度（字符）
TOOL_EXECUTION_TIMEOUT = 600.0  # 工具执行硬超时（秒）—— 图片/视频生成需要 3-10 分钟

# ── Agent 工具循环（agent.py）───────────────────────────────

MAX_TOOL_ITERATIONS = 10  # 自定义工具暂停-继续循环最大轮次（可通过 llm_config 配置）
CONFIG_MAX_TOOL_ITERATIONS = "max_tool_iterations"  # 持久化配置键

# ── 视频合成器（composer/ 包）───────────────────────────────

COMPOSER_ID_LENGTH = 12                 # composer 各类 ID 字符长度
COMPOSER_ID_PREFIX_ASSET = "as_"        # 素材 ID 前缀
COMPOSER_ID_PREFIX_PROJECT = "pr_"      # 项目 ID 前缀（M2 启用）
COMPOSER_ID_PREFIX_RENDER = "rd_"       # 渲染 ID 前缀（M3 启用）

MB_BYTES = 1024 * 1024                  # 兆字节换算（uploads / composer 共用）

COMPOSER_KIND_VIDEO = "video"
COMPOSER_KIND_IMAGE = "image"
COMPOSER_KIND_AUDIO = "audio"
COMPOSER_KIND_UNKNOWN = "unknown"

COMPOSER_SOURCE_UPLOAD = "upload"       # 本地上传
COMPOSER_SOURCE_URL = "url"             # URL 导入

COMPOSER_MAX_UPLOAD_SIZE = 500 * MB_BYTES  # 素材上传 / URL 下载上限（500 MB）
COMPOSER_DISK_LIMIT_BYTES = 5 * 1024 * MB_BYTES  # data/composer 磁盘水位上限（5 GB，M3 告警）
COMPOSER_RENDER_CONCURRENCY = 1         # 渲染并发（M3 启用）
COMPOSER_HTTP_TIMEOUT = 300.0           # 素材 URL 下载超时（秒）—— 大文件需要较长窗口
COMPOSER_PROBE_TIMEOUT = 30.0           # ffprobe 子进程超时（秒）
COMPOSER_HASH_CHUNK = 1024 * 1024       # sha256 分块大小（1 MB）
COMPOSER_STREAM_CHUNK = 1024 * 1024     # Range 流式响应分块大小（1 MB）

COMPOSER_SSE_ASSET = "composer_asset"       # SSE：素材入库 / 删除
COMPOSER_SSE_CONNECTED = "composer_connected"  # SSE：连接快照
COMPOSER_SSE_HEARTBEAT = 15.0                # composer SSE 心跳间隔（秒）

# 素材 MIME 白名单：扩展名 → (kind, Content-Type)
COMPOSER_MEDIA_EXTS: dict[str, tuple[str, str]] = {
    # 图片
    ".jpg": (COMPOSER_KIND_IMAGE, "image/jpeg"),
    ".jpeg": (COMPOSER_KIND_IMAGE, "image/jpeg"),
    ".png": (COMPOSER_KIND_IMAGE, "image/png"),
    ".gif": (COMPOSER_KIND_IMAGE, "image/gif"),
    ".webp": (COMPOSER_KIND_IMAGE, "image/webp"),
    ".bmp": (COMPOSER_KIND_IMAGE, "image/bmp"),
    # 视频
    ".mp4": (COMPOSER_KIND_VIDEO, "video/mp4"),
    ".mov": (COMPOSER_KIND_VIDEO, "video/quicktime"),
    ".mkv": (COMPOSER_KIND_VIDEO, "video/x-matroska"),
    ".webm": (COMPOSER_KIND_VIDEO, "video/webm"),
    ".avi": (COMPOSER_KIND_VIDEO, "video/x-msvideo"),
    # 音频
    ".mp3": (COMPOSER_KIND_AUDIO, "audio/mpeg"),
    ".wav": (COMPOSER_KIND_AUDIO, "audio/wav"),
    ".m4a": (COMPOSER_KIND_AUDIO, "audio/mp4"),
    ".aac": (COMPOSER_KIND_AUDIO, "audio/aac"),
    ".flac": (COMPOSER_KIND_AUDIO, "audio/flac"),
    ".ogg": (COMPOSER_KIND_AUDIO, "audio/ogg"),
}

# 分辨率预设表（M2/M3 使用，M1 仅入配置）
COMPOSER_PRESET_DEFAULT = "720p16x9"
COMPOSER_PRESETS: dict[str, dict[str, int]] = {
    "720p16x9": {"width": 1280, "height": 720, "fps": 30},
    "1080p16x9": {"width": 1920, "height": 1080, "fps": 30},
    "720p9x16": {"width": 720, "height": 1280, "fps": 30},
    "1080p9x16": {"width": 1080, "height": 1920, "fps": 30},
    "720p1x1": {"width": 720, "height": 720, "fps": 30},
}

# ── MCP（mcp.py）───────────────────────────────────────────

MCP_INIT_TIMEOUT = 60.0          # MCP 服务器初始化握手超时（秒）—— 首次 npx 下载可能需 20-30s
MCP_LIST_TOOLS_TIMEOUT = 8.0     # 工具发现超时（秒）
MCP_CALL_TOOL_TIMEOUT = 600.0    # 工具调用超时（秒）—— 图片/视频生成需要 3-10 分钟
MCP_SHUTDOWN_TIMEOUT = 5.0       # MCP 进程优雅关闭等待超时（秒）
MCP_HTTP_TIMEOUT = 30.0           # MCP HTTP 请求超时（秒）
MCP_RETRY_INTERVAL = 120.0        # 健康检查自动重连冷却（秒）—— 避免对持续故障的服务器频繁重试

# LLM 健康检查状态 ID（health_check 返回值，前端映射为展示文案）
HEALTH_HEALTHY = "healthy"
HEALTH_NO_DEFAULT_MODEL = "no_default_model"
HEALTH_UNHEALTHY = "unhealthy"
HEALTH_UNREACHABLE = "unreachable"
HEALTH_UNKNOWN = "unknown"

# MCP 服务器连接状态 ID（get_status 返回值，前端映射为展示文案）
MCP_RUNNING = "running"
MCP_STOPPED = "stopped"
MCP_ERROR = "error"

# ── 文件上传（uploads.py）─────────────────────────────────

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 最大上传大小（10 MB）
MAX_TEXT_LENGTH = 80_000             # 提取文本最大长度（~20K tokens）

# ── CORS（main.py）─────────────────────────────────────────

CORS_ORIGIN = "*"  # 允许所有来源（局域网访问）

# ── LLM 配置持久化键（config.py / router.py）───────────────

CONFIG_BASE_URL = "base_url"
CONFIG_AUTH_TOKEN = "auth_token"
CONFIG_MODEL = "model"
CONFIG_MAX_CONCURRENT = "max_concurrent"
CONFIG_SYSTEM_PROMPT = "system_prompt"
CONFIG_TEMPERATURE = "temperature"
CONFIG_MAX_TOKENS = "max_tokens"
CONFIG_TOP_P = "top_p"
CONFIG_TOP_K = "top_k"
CONFIG_PRESENCE_PENALTY = "presence_penalty"
CONFIG_FREQUENCY_PENALTY = "frequency_penalty"
CONFIG_REPEAT_PENALTY = "repeat_penalty"

# ── MCP JSON 配置键（config.py / mcp.py）────────────────────

MCP_KEY_MCP_SERVERS = "mcpServers"
MCP_KEY_COMMAND = "command"
MCP_KEY_ARGS = "args"
MCP_KEY_ENV = "env"
MCP_KEY_TRANSPORT = "transport"
MCP_KEY_URL = "url"
MCP_KEY_DISABLED = "disabled"
MCP_KEY_HEADERS = "headers"
MCP_KEY_NAME = "name"
MCP_TRANSPORT_STDIO = "stdio"
MCP_TRANSPORT_HTTP = "http"

# ── JSON-RPC 协议字符串（mcp.py）─────────────────────────────

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_METHOD_INITIALIZE = "initialize"
MCP_METHOD_INITIALIZED = "notifications/initialized"
MCP_METHOD_TOOLS_LIST = "tools/list"
MCP_METHOD_TOOLS_CALL = "tools/call"

# ── MCP 结果字段（mcp.py）───────────────────────────────────

MCP_FIELD_TYPE = "type"
MCP_FIELD_TEXT = "text"
MCP_FIELD_RESOURCE = "resource"
MCP_FIELD_CONTENT = "content"
MCP_FIELD_IS_ERROR = "isError"
MCP_FIELD_INPUT_SCHEMA = "inputSchema"
MCP_FIELD_SERVER_INFO = "serverInfo"
MCP_FIELD_CLIENT_INFO = "clientInfo"
MCP_FIELD_RESULT = "result"
MCP_FIELD_ERROR = "error"

# ── MIME / Content-Type（client.py / mcp.py / uploads.py）────

CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_EVENT_STREAM = "text/event-stream"
CONTENT_TYPE_OCTET_STREAM = "application/octet-stream"
CONTENT_TYPE_TEXT = "text/plain"
ACCEPT_HEADER_SSE = "application/json, text/event-stream"
DATA_URL_PREFIX = "data:{};base64,"

# ── 中文提示消息（sessions.py / router.py）───────────────────

MSG_SESSION_NOT_FOUND = "会话不存在"
MSG_AGENT_SESSION_NOT_FOUND = "Agent 会话不存在"
MSG_BUILTIN_GROUP = "内置"
MSG_MAX_ITERATIONS = "已达到工具调用轮次上限，推理中止。请基于以上工具结果继续提问，或开启新对话。"
MSG_EMPTY_REPLY = "（模型未返回文本内容，请重试或调整提问方式。）"

# ── API 响应键（info.py / router.py）─────────────────────────

RESPONSE_KEY_OK = "ok"
SSE_KEY_SESSION_ID = "session_id"
SSE_KEY_LAST_ACCESS = "last_access"
SSE_KEY_TOOL_NAME = "name"
SSE_KEY_TOOL_ARGS = "arguments"
SSE_KEY_TOOL_RESULT = "result"
SSE_KEY_IS_ERROR = "is_error"
