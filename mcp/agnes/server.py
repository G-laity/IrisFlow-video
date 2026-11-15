"""Agnes AI MCP Server -- Image 2.1 Flash + Video 2.5（中国站）

默认使用中国站 Base URL（api.agnes-ai.cn），海外部署可用环境变量
AGNES_BASE_URL 覆盖。视频模型默认为 agnes-video-2.5（AGNES_VIDEO_MODEL
可覆盖为 agnes-video-2.5-flash）。

Transport:
    stdio (default):  MCP_TRANSPORT=stdio  or omit
    SSE (HTTP):       MCP_TRANSPORT=sse    -> http://localhost:9103/sse
"""

import os

import httpx
from fastmcp import FastMCP

# 默认国内地址（api.agnes-ai.cn）；海外部署可通过 AGNES_BASE_URL 覆盖
AGNES_BASE = os.environ.get("AGNES_BASE_URL", "https://api.agnes-ai.cn")
# 视频模型（国内站）；720P 免费，可用 AGNES_VIDEO_MODEL 覆盖
VIDEO_MODEL = os.environ.get("AGNES_VIDEO_MODEL", "agnes-video-2.5-flash")

# -- Constants (per official docs) ---------------------------------

IMAGE_SIZES = {"1K", "2K", "3K", "4K"}
IMAGE_RATIOS = {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"}
RESPONSE_FORMATS = {"url", "b64_json"}

mcp = FastMCP("agnes-ai")


def _api_key() -> str:
    key = os.environ.get("AGNES_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AGNES_API_KEY environment variable is not set")
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


# -- Image --------------------------------------------------------


@mcp.tool()
async def agnes_image_generate(
    prompt: str,
    size: str = "2K",
    ratio: str = "1:1",
    response_format: str = "url",
    image: str = "",
    return_base64: bool = False,
) -> str:
    """Generate an image using Agnes Image 2.1 Flash.

    Supports text-to-image and image-to-image (when `image` is provided
    with a public URL or data URI).

    Args:
        prompt: Text description of the desired image.
        size: Output size tier: "1K", "2K", "3K", or "4K". Default "2K".
        ratio: Aspect ratio: "1:1", "3:4", "4:3", "16:9", "9:16", "2:3",
               "3:2", "21:9". Default "1:1".
        response_format: Output format: "url" (default) or "b64_json".
        image: Public image URL or data URI for image-to-image mode.
            Leave empty for text-to-image.
        return_base64: For text-to-image, set to True to get base64
            instead of URL. For img2img, set response_format="b64_json".
    """
    try:
        if size not in IMAGE_SIZES:
            return f"Invalid size '{size}'. Must be one of: {', '.join(sorted(IMAGE_SIZES))}"
        if ratio not in IMAGE_RATIOS:
            return f"Invalid ratio '{ratio}'. Must be one of: {', '.join(sorted(IMAGE_RATIOS))}"
        if response_format not in RESPONSE_FORMATS:
            return f"Invalid response_format '{response_format}'. Must be one of: {', '.join(sorted(RESPONSE_FORMATS))}"

        # response_format always lives inside extra_body per the API docs
        extra_body: dict = {"response_format": response_format}

        # Image-to-image: input image array goes inside extra_body
        if image:
            extra_body["image"] = [image]

        body: dict = {
            "model": "agnes-image-2.1-flash",
            "prompt": prompt,
            "size": size,
            "ratio": ratio,
            "extra_body": extra_body,
        }

        # Text-to-image base64: use top-level return_base64 flag
        if return_base64 and not image:
            body["return_base64"] = True

        async with httpx.AsyncClient(timeout=httpx.Timeout(360, connect=30)) as client:
            resp = await client.post(
                f"{AGNES_BASE}/v1/images/generations",
                headers=_headers(),
                json=body,
            )
            if not resp.is_success:
                return f"Agnes API error {resp.status_code}: {resp.text}"
            try:
                return str(resp.json())
            except Exception:
                return f"Agnes API returned non-JSON response ({resp.status_code}): {resp.text[:1000]}"
    except httpx.TimeoutException:
        return "Agnes API request timed out after 360 s."
    except Exception as exc:
        return f"Unexpected error in agnes_image_generate: {exc}"


# -- Video --------------------------------------------------------


@mcp.tool()
async def agnes_video_create(
    prompt: str,
    mode: str = "text",
    seconds: str = "5",
    size: str = "720P",
    aspect_ratio: str = "16:9",
    seed: int = 0,
    first_frame: str = "",
    last_frame: str = "",
    images: str = "",
    audios: str = "",
    videos: str = "",
) -> str:
    """Create a video generation task using Agnes Video 2.5 (async).

    The task runs asynchronously. Use agnes_video_status to poll for
    completion. Returns the creation response which includes `video_id`.

    Args:
        prompt: Text description of the video content.
        mode: Generation mode: "text" (pure text-to-video), "keyframe"
            (control start/end frame with first_frame/last_frame), or
            "reference" (use images/audios/videos as reference). Default "text".
        seconds: Video duration as string, "4" to "12". Default "5".
        size: Output resolution tier: "720P", "1080P", "1K", or "2K".
            Default "720P".
        aspect_ratio: Aspect ratio, e.g. "16:9", "9:16", "1:1". Default "16:9".
        seed: Random seed for reproducibility (0 = random).
        first_frame: (keyframe mode) Public image URL for the first frame.
            At least one of first_frame/last_frame is required in keyframe mode.
        last_frame: (keyframe mode) Public image URL for the last frame.
        images: (reference mode) Comma-separated public image URLs
            (max 8). Reference media must be publicly accessible.
        audios: (reference mode) Comma-separated public audio URLs (max 3).
        videos: (reference mode) Comma-separated public video URLs (max 1).
    """
    try:
        VIDEO_MODES = {"text", "keyframe", "reference"}
        VIDEO_SIZES = {"720P", "1080P", "1K", "2K"}
        VIDEO_SECONDS = {str(s) for s in range(4, 13)}

        if mode not in VIDEO_MODES:
            return f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(VIDEO_MODES))}"
        if size not in VIDEO_SIZES:
            return f"Invalid size '{size}'. Must be one of: {', '.join(sorted(VIDEO_SIZES))}"
        if seconds not in VIDEO_SECONDS:
            return f"Invalid seconds '{seconds}'. Must be a string from \"4\" to \"12\"."

        payload: dict = {
            "model": VIDEO_MODEL,
            "prompt": prompt,
            "mode": mode,
            "seconds": seconds,
            "size": size,
            "aspect_ratio": aspect_ratio,
        }
        if seed:
            payload["seed"] = seed

        # Mode-specific media fields (per official docs)
        if mode == "keyframe":
            if not first_frame and not last_frame:
                return "keyframe mode requires at least one of first_frame / last_frame."
            if first_frame:
                payload["first_frame"] = first_frame
            if last_frame:
                payload["last_frame"] = last_frame
        elif mode == "reference":
            if not (images or audios or videos):
                return "reference mode requires at least one of images / audios / videos."
            if images:
                payload["images"] = [u.strip() for u in images.split(",") if u.strip()]
            if audios:
                payload["audios"] = [u.strip() for u in audios.split(",") if u.strip()]
            if videos:
                payload["videos"] = [
                    {"url": u.strip()}
                    for u in videos.split(",") if u.strip()
                ]

        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=30)) as client:
            resp = await client.post(
                f"{AGNES_BASE}/v1/videos",
                headers=_headers(),
                json=payload,
            )
            if not resp.is_success:
                return f"Agnes API error {resp.status_code}: {resp.text}"
            try:
                return str(resp.json())
            except Exception:
                return f"Agnes API returned non-JSON response ({resp.status_code}): {resp.text[:1000]}"
    except httpx.TimeoutException:
        return "Agnes API request timed out after 60 s."
    except Exception as exc:
        return f"Unexpected error in agnes_video_create: {exc}"


@mcp.tool()
async def agnes_video_status(
    video_id: str,
    model_name: str = "",
) -> str:
    """Poll the status of an Agnes Video 2.5 generation task.

    Uses the recommended /agnesapi endpoint with model_name (suggested
    by official docs: poll every 1-2 seconds until status becomes
    "completed" or "failed"). When the task completes, the final video
    URL is in the response `url` field.

    Args:
        video_id: The video_id returned by agnes_video_create.
        model_name: Model name used for creation; defaults to the
            configured VIDEO_MODEL when empty.
    """
    try:
        params: dict = {
            "video_id": video_id,
            "model_name": model_name or VIDEO_MODEL,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=15)) as client:
            resp = await client.get(
                f"{AGNES_BASE}/agnesapi",
                headers=_headers(),
                params=params,
            )
            if not resp.is_success:
                return f"Agnes API error {resp.status_code}: {resp.text}"
            try:
                return str(resp.json())
            except Exception:
                return f"Agnes API returned non-JSON response ({resp.status_code}): {resp.text[:1000]}"
    except httpx.TimeoutException:
        return "Agnes API request timed out after 30 s."
    except Exception as exc:
        return f"Unexpected error in agnes_video_status: {exc}"


# -- Entry --------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
