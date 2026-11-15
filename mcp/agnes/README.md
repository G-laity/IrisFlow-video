# Agnes AI MCP Server

基于 [FastMCP](https://github.com/jlowin/fastmcp) 的 MCP 服务器，接入 Agnes AI 图像与视频生成服务。

## 支持的服务

| 工具 | 模型 | 说明 |
|------|------|------|
| `agnes_image_generate` | Agnes Image 2.1 Flash | 文生图 / 图生图，支持 URL 与 Base64 输出 |
| `agnes_video_create` | Agnes Video V2.0 | 创建异步视频生成任务（文生视频 / 图生视频 / 关键帧动画） |
| `agnes_video_status` | Agnes Video V2.0 | 查询视频任务进度与结果 |

## 快速开始

```bash
cd mcp/agnes
uv sync
```

### stdio 模式（默认，IrisFlow 集成用）

```bash
AGNES_API_KEY=sk-xxx uv run server.py
```

### SSE HTTP 模式（独立调试用）

```bash
MCP_TRANSPORT=sse AGNES_API_KEY=sk-xxx uv run server.py
# 监听 http://localhost:9103/sse
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `AGNES_API_KEY` | ✅ | Agnes AI API Key |
| `MCP_TRANSPORT` | — | 传输协议：`stdio`（默认）或 `sse` |

## 工具参数

### agnes_image_generate

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | string | (必填) | 图像描述 |
| `size` | string | `"2K"` | `1K` / `2K` / `3K` / `4K` |
| `ratio` | string | `"1:1"` | `1:1` / `3:4` / `4:3` / `16:9` / `9:16` / `2:3` / `3:2` / `21:9` |
| `response_format` | string | `"url"` | `url` 或 `b64_json` |
| `image` | string | `""` | 图生图的输入图像 URL 或 data URI |
| `return_base64` | bool | `false` | 文生图时用 Base64 返回（图生图请设 `response_format="b64_json"`） |

### agnes_video_create

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | string | (必填) | 视频内容描述 |
| `width` | int | `1152` | 视频宽度 (px) |
| `height` | int | `768` | 视频高度 (px) |
| `num_frames` | int | `121` | 帧数，≤441 且遵循 8n+1 规则 |
| `frame_rate` | float | `24.0` | 帧率，1–60 |
| `mode` | string | `""` | `ti2vid` 或 `keyframes` |
| `image` | string | `""` | 图生视频的输入图像 URL |
| `keyframe_images` | string | `""` | 关键帧图像 URL，逗号分隔 |
| `num_inference_steps` | int | `0` | 推理步数（0=模型默认） |
| `seed` | int | `0` | 随机种子（0=随机） |
| `negative_prompt` | string | `""` | 反向提示词 |

### agnes_video_status

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `video_id` | string | (必填) | 创建任务返回的 video_id |
| `model_name` | string | `""` | 可选，指定模型名称 |
