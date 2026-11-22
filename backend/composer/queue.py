"""渲染任务队列与状态机（M3）。

FIFO + 并发 worker（配置 render_concurrency）。分期渲染：
  preparing（逐镜头规格化）→ rendering（concat）→ muxing（字幕 + 音轨）→ completed
任意阶段可取消（杀 ffmpeg 子进程），异常进 failed（stderr 尾部入库）。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

from composer import assets as composer_assets
from composer import config as composer_config
from composer import ffmpeg as composer_ffmpeg
from composer import timeline as composer_timeline
from composer.store import composer_store
from llm.constants import (
    MB_BYTES,
    MSG_RENDER_ALREADY_ACTIVE,
    MSG_RENDER_CANCEL_REQUESTED,
    MSG_RENDER_DISK_WARN,
    MSG_RENDER_FFMPEG_MISSING,
    MSG_RENDER_INTERRUPTED,
    MSG_RENDER_NO_SEGMENTS,
    RENDER_CANCELED,
    RENDER_CANCEL_GRACE,
    RENDER_COMPLETED,
    RENDER_CONCAT_LIST_NAME,
    RENDER_DIR,
    RENDER_FAILED,
    RENDER_LOG_PREFIX,
    RENDER_MUXING,
    RENDER_OUTPUT_NAME,
    RENDER_PREPARING,
    RENDER_PROGRESS_CONCAT,
    RENDER_PROGRESS_PREPARING,
    RENDER_PROGRESS_THROTTLE,
    RENDER_QUEUED,
    RENDER_RENDERING,
    RENDER_SEGMENT_DIR,
    RENDER_SEGMENT_PATTERN,
    RENDER_SUBTITLES_NAME,
    TRACK_AUDIO,
    TRACK_VIDEO,
    TRACK_SUBTITLES,
)

_log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "composer"
_LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class RenderCanceled(Exception):
    """内部取消信号。"""


class RenderQueue:
    """渲染队列单例。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._live: dict[str, dict[str, object]] = {}
        self._cancel: set[str] = set()
        self._last_emit: dict[str, float] = {}
        self._started = False

    # ── 生命周期 ─────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        await composer_store.reset_interrupted_renders()
        concurrency = max(1, composer_config.get_render_concurrency())
        self._started = True
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"composer-render-{i}")
            for i in range(concurrency)
        ]
        _log.info("渲染队列启动: concurrency=%d", concurrency)

    async def shutdown(self) -> None:
        self._started = False
        for proc in list(self._procs.values()):
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._procs.clear()
        _log.info("渲染队列已关闭")

    # ── 提交 / 取消 / 查询 ───────────────────────────

    async def submit(self, project_id: str) -> dict[str, object]:
        """校验项目与时间轴，创建渲染任务并入队。"""
        if not composer_ffmpeg.ffmpeg_available:
            await composer_ffmpeg.refresh_availability(composer_config.get_ffmpeg_path())
            if not composer_ffmpeg.ffmpeg_available:
                raise RuntimeError(MSG_RENDER_FFMPEG_MISSING)
        project = await composer_store.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        timeline = project.get("timeline")
        tracks = timeline.get("tracks") if isinstance(timeline, dict) else None
        segments = tracks.get(TRACK_VIDEO) if isinstance(tracks, dict) else None
        if not isinstance(segments, list) or not segments:
            raise ValueError(MSG_RENDER_NO_SEGMENTS)
        if await composer_store.has_active_render(project_id):
            raise ValueError(MSG_RENDER_ALREADY_ACTIVE)

        render = await composer_store.create_render(project_id)
        render_id = str(render["render_id"])
        self._live[render_id] = {
            "state": RENDER_QUEUED,
            "progress": 0.0,
            "stage_detail": {"total_segments": len(segments), "done_segments": 0, "current": "queued"},
        }
        await self._queue.put(render_id)
        await self._emit_render(render_id)
        return render

    async def cancel(self, render_id: str) -> dict[str, object] | None:
        render = await composer_store.get_render(render_id)
        if render is None:
            return None
        state = str(render["state"])
        if state == RENDER_QUEUED:
            await composer_store.update_render(
                render_id, state=RENDER_CANCELED, error=MSG_RENDER_CANCEL_REQUESTED, finished=True
            )
            self._live[render_id] = {"state": RENDER_CANCELED, "progress": 0.0, "stage_detail": {"current": "canceled"}}
            await self._emit_render(render_id)
            return await composer_store.get_render(render_id)
        if state not in (RENDER_PREPARING, RENDER_RENDERING, RENDER_MUXING):
            return render

        self._cancel.add(render_id)
        proc = self._procs.get(render_id)
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=RENDER_CANCEL_GRACE)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        return await composer_store.get_render(render_id)

    def live_snapshot(self, render_id: str) -> dict[str, object] | None:
        return self._live.get(render_id)

    # ── worker / 执行 ────────────────────────────────

    async def _worker(self, index: int) -> None:
        while True:
            render_id = await self._queue.get()
            try:
                await self._execute(render_id)
            except asyncio.CancelledError:
                break
            except Exception:
                _log.exception("渲染 worker #%d 未捕获异常: %s", index, render_id)
            finally:
                self._queue.task_done()

    async def _execute(self, render_id: str) -> None:
        render = await composer_store.get_render(render_id)
        if render is None:
            return
        if str(render["state"]) not in (RENDER_QUEUED,):
            return  # 入队后已被取消
        project = await composer_store.get_project(str(render["project_id"]))
        if project is None:
            await self._fail(render_id, "项目不存在")
            return

        render_dir = _DATA_DIR / RENDER_DIR / render_id
        segments_dir = render_dir / RENDER_SEGMENT_DIR
        log_path = _LOGS_DIR / f"{RENDER_LOG_PREFIX}{render_id}.log"
        try:
            await self._run_pipeline(render_id, project, render_dir, segments_dir, log_path)
        except RenderCanceled:
            await self._finish(render_id, RENDER_CANCELED, MSG_RENDER_CANCEL_REQUESTED)
            _log.info("渲染已取消: %s", render_id)
        except asyncio.CancelledError:
            await self._finish(render_id, RENDER_FAILED, MSG_RENDER_INTERRUPTED)
            raise
        except Exception as e:
            if render_id in self._cancel:
                await self._finish(render_id, RENDER_CANCELED, MSG_RENDER_CANCEL_REQUESTED)
                _log.info("渲染已取消: %s", render_id)
            else:
                _log.warning("渲染失败 %s: %s", render_id, e)
                await self._finish(render_id, RENDER_FAILED, str(e)[:2000])
        finally:
            self._procs.pop(render_id, None)
            self._cancel.discard(render_id)

    async def _run_pipeline(
        self,
        render_id: str,
        project: dict[str, object],
        render_dir: Path,
        segments_dir: Path,
        log_path: Path,
    ) -> None:
        timeline_obj = project.get("timeline")
        if not isinstance(timeline_obj, dict):
            raise RuntimeError("项目时间轴为空")
        timeline: dict[str, object] = timeline_obj
        tracks_obj = timeline.get("tracks")
        tracks: dict[str, object] = tracks_obj if isinstance(tracks_obj, dict) else {}
        segments = tracks.get(TRACK_VIDEO)
        segments = segments if isinstance(segments, list) else []
        if not segments:
            raise RuntimeError(MSG_RENDER_NO_SEGMENTS)

        preset_name = str(timeline.get("preset") or "")
        presets = composer_config.get_presets()
        preset = presets.get(preset_name)
        if preset is None:
            raise RuntimeError(f"未知分辨率预设: {preset_name}")

        assets = {str(a["asset_id"]): a for a in await composer_store.list_assets()}
        segments_dir.mkdir(parents=True, exist_ok=True)
        render_dir.mkdir(parents=True, exist_ok=True)

        total = len(segments)
        seg_paths: list[Path] = []
        total_duration = 0.0

        await self._set_state(
            render_id, RENDER_PREPARING, 0.0,
            {"total_segments": total, "done_segments": 0, "current": f"segment 0/{total}"},
        )

        # ── preparing：逐镜头规格化 ────────────────
        for i, seg in enumerate(segments):
            if render_id in self._cancel:
                raise RenderCanceled()
            if not isinstance(seg, dict):
                raise RuntimeError(f"tracks.video[{i}] 非法")
            asset = assets.get(str(seg.get("asset_id") or ""))
            if asset is None:
                raise RuntimeError(f"tracks.video[{i}].asset_id 对应素材不存在")
            duration = float(seg.get("duration") or 0.0)
            if duration <= 0:
                raise RuntimeError(f"tracks.video[{i}].duration 必须为正数")
            kind = str(asset.get("kind"))
            asset_path = composer_assets.asset_abs_path(str(asset["file_path"]))
            if not asset_path.is_file():
                raise RuntimeError(f"素材文件缺失: {asset_path}")
            out_path = segments_dir / (RENDER_SEGMENT_PATTERN % i)
            cmd = composer_ffmpeg.build_segment_cmd(
                asset_path, kind, duration, float(seg.get("trim_in") or 0.0), preset, out_path
            )

            def _on_progress(frac: float, idx: int = i) -> None:
                overall = (idx + frac) / total * RENDER_PROGRESS_PREPARING
                self._update_progress(
                    render_id, overall,
                    {"total_segments": total, "done_segments": idx, "current": f"segment {idx + 1}/{total}"},
                )

            await composer_ffmpeg.run_ffmpeg(
                cmd, duration=duration, log_path=log_path,
                on_progress=_on_progress,
                register_proc=lambda p, rid=render_id: self._register_proc(rid, p),
            )
            seg_paths.append(out_path)
            total_duration += duration
            self._update_progress(
                render_id, (i + 1) / total * RENDER_PROGRESS_PREPARING,
                {"total_segments": total, "done_segments": i + 1, "current": f"segment {i + 1}/{total}"},
            )

        if render_id in self._cancel:
            raise RenderCanceled()

        # ── rendering：concat ─────────────────────
        await self._set_state(
            render_id, RENDER_RENDERING, RENDER_PROGRESS_PREPARING,
            {"total_segments": total, "done_segments": total, "current": "concat"},
        )
        list_path = render_dir / RENDER_CONCAT_LIST_NAME
        list_path.write_text(
            "".join(f"file '{RENDER_SEGMENT_DIR}/{p.name}'\n" for p in seg_paths),
            encoding="utf-8",
        )
        merged_path = render_dir / "merged.mp4"
        await composer_ffmpeg.run_ffmpeg(
            composer_ffmpeg.build_concat_cmd(Path(RENDER_CONCAT_LIST_NAME), Path("merged.mp4")),
            cwd=render_dir, log_path=log_path,
            register_proc=lambda p: self._register_proc(render_id, p),
        )
        self._update_progress(
            render_id, RENDER_PROGRESS_CONCAT,
            {"total_segments": total, "done_segments": total, "current": "muxing"},
        )

        if render_id in self._cancel:
            raise RenderCanceled()

        # ── muxing：字幕 + 音频 ───────────────────
        await self._set_state(
            render_id, RENDER_MUXING, RENDER_PROGRESS_CONCAT,
            {"total_segments": total, "done_segments": total, "current": "muxing"},
        )
        subtitle_name: str | None = None
        subs = tracks.get(TRACK_SUBTITLES)
        if isinstance(subs, list) and subs:
            srt = composer_timeline.generate_srt([s for s in subs if isinstance(s, dict)])
            if srt.strip():
                (render_dir / RENDER_SUBTITLES_NAME).write_text(srt, encoding="utf-8")
                subtitle_name = RENDER_SUBTITLES_NAME

        audio_tracks: list[dict[str, object]] = []
        audio_entries = tracks.get(TRACK_AUDIO)
        if isinstance(audio_entries, list):
            for track in audio_entries:
                if not isinstance(track, dict):
                    continue
                audio_asset = assets.get(str(track.get("asset_id") or ""))
                if audio_asset is None:
                    continue
                path = composer_assets.asset_abs_path(str(audio_asset["file_path"]))
                if not path.is_file():
                    continue
                audio_tracks.append({
                    "path": path,
                    "role": track.get("role"),
                    "start": float(track.get("start") or 0.0),
                    "duration": float(track.get("duration") or 0.0),
                    "gain": float(track.get("gain") or 1.0),
                    "fade_in": float(track.get("fade_in") or 0.0),
                    "fade_out": float(track.get("fade_out") or 0.0),
                    "loop": bool(track.get("loop")),
                })

        def _on_mux_progress(frac: float) -> None:
            overall = RENDER_PROGRESS_CONCAT + frac * (1.0 - RENDER_PROGRESS_CONCAT)
            self._update_progress(
                render_id, overall,
                {"total_segments": total, "done_segments": total, "current": "muxing"},
            )

        await composer_ffmpeg.run_ffmpeg(
            composer_ffmpeg.build_mux_cmd(
                Path("merged.mp4"), Path(RENDER_OUTPUT_NAME), subtitle_name, audio_tracks, total_duration
            ),
            duration=total_duration, cwd=render_dir, log_path=log_path,
            on_progress=_on_mux_progress,
            register_proc=lambda p: self._register_proc(render_id, p),
        )

        output_rel = f"{RENDER_DIR}/{render_id}/{RENDER_OUTPUT_NAME}"
        output_abs = _DATA_DIR / output_rel
        if not output_abs.is_file():
            raise RuntimeError("渲染完成但输出文件不存在")

        # 清理中间文件（保留 output.mp4 与 SRT）
        shutil.rmtree(segments_dir, ignore_errors=True)
        merged_path.unlink(missing_ok=True)
        list_path.unlink(missing_ok=True)

        self._live[render_id] = {
            "state": RENDER_COMPLETED, "progress": 1.0,
            "stage_detail": {"total_segments": total, "done_segments": total, "current": "completed"},
        }
        await composer_store.update_render(
            render_id, state=RENDER_COMPLETED, progress=1.0,
            stage_detail={"total_segments": total, "done_segments": total, "current": "completed"},
            output_path=output_rel, error="", finished=True,
        )
        await self._emit_render(render_id)
        _log.info("渲染完成: %s → %s", render_id, output_rel)
        await self._check_disk_watermark()

    # ── 辅助 ─────────────────────────────────────────

    def _register_proc(self, render_id: str, proc: asyncio.subprocess.Process | None) -> None:
        if proc is None:
            self._procs.pop(render_id, None)
        else:
            self._procs[render_id] = proc

    def _update_progress(self, render_id: str, progress: float, stage_detail: dict[str, object]) -> None:
        live = self._live.setdefault(render_id, {"state": RENDER_PREPARING, "progress": 0.0, "stage_detail": {}})
        live["progress"] = max(0.0, min(1.0, progress))
        live["stage_detail"] = stage_detail
        now = time.monotonic()
        last = self._last_emit.get(render_id, 0.0)
        if now - last >= RENDER_PROGRESS_THROTTLE:
            self._last_emit[render_id] = now
            asyncio.create_task(self._emit_progress(render_id))

    async def _set_state(
        self, render_id: str, state: str, progress: float, stage_detail: dict[str, object]
    ) -> None:
        self._live[render_id] = {"state": state, "progress": progress, "stage_detail": stage_detail}
        await composer_store.update_render(
            render_id, state=state, progress=progress, stage_detail=stage_detail
        )
        await self._emit_render(render_id)

    async def _finish(self, render_id: str, state: str, error: str) -> None:
        live = self._live.setdefault(render_id, {"state": state, "progress": 0.0, "stage_detail": {}})
        live["state"] = state
        live["stage_detail"] = {"current": state}
        await composer_store.update_render(
            render_id, state=state, error=error or "", finished=True
        )
        await self._emit_render(render_id)

    async def _fail(self, render_id: str, error: str) -> None:
        await self._finish(render_id, RENDER_FAILED, error)

    async def _emit_render(self, render_id: str) -> None:
        try:
            from composer.router import broadcast_render

            await broadcast_render(render_id, self._live.get(render_id))
        except Exception:
            pass  # SSE 广播失败不影响渲染

    async def _emit_progress(self, render_id: str) -> None:
        try:
            from composer.router import broadcast_progress

            live = self._live.get(render_id) or {}
            await broadcast_progress(
                render_id, _to_float(live.get("progress")),
                str(live.get("state") or ""), live.get("stage_detail") or {},
            )
        except Exception:
            pass

    async def _check_disk_watermark(self) -> None:
        used = composer_assets.disk_usage_bytes()
        limit = composer_config.get_disk_limit_bytes()
        if used > limit:
            try:
                from composer.router import broadcast_warn

                await broadcast_warn(MSG_RENDER_DISK_WARN.format(
                    used=round(used / (1024 * MB_BYTES), 2),
                    limit=round(limit / (1024 * MB_BYTES), 2),
                ))
            except Exception:
                pass


render_queue = RenderQueue()
