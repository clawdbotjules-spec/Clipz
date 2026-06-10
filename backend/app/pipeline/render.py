"""ffmpeg rendering: cut -> 9:16 smart crop -> -14 LUFS -> burned captions.

Two-pass design for fast hook edits:
  1. base pass  - cut + crop/blur + loudness normalize -> cached "base" mp4 (no text)
  2. text pass  - burn ASS captions/hook (+ optional watermark) onto the base

Editing the hook headline only re-runs the cheap text pass.
"""
from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..config import get_settings
from ..errors import RenderError
from .captions import build_ass
from .facetrack import find_face_center_x

OUT_W, OUT_H = 1080, 1920
FPS = 30


def _run_ffmpeg(args: list[str], what: str) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise RenderError(
            "ffmpeg is not installed or not on PATH. See README for install steps."
        ) from e
    if proc.returncode != 0:
        raise RenderError(
            f"Render failed during {what}. See server logs for the ffmpeg error.",
            detail=f"cmd: {shlex.join(cmd)}\nstderr: {proc.stderr[-2000:]}",
        )


def _measure_loudness(path: str, start: float, end: float) -> dict[str, str] | None:
    """First loudnorm pass: measure so the second pass can normalize linearly."""
    cmd = [
        "ffmpeg", "-v", "info", "-nostats",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", path,
        "-vn", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    # loudnorm prints its JSON blob at the end of stderr
    stderr = proc.stderr
    brace = stderr.rfind("{")
    if brace == -1:
        return None
    try:
        return json.loads(stderr[brace:stderr.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _loudnorm_filter(measured: dict[str, str] | None) -> str:
    base = "loudnorm=I=-14:TP=-1.5:LRA=11"
    if measured:
        return (
            f"{base}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured.get('target_offset', '0')}:linear=true"
        )
    return base


def _crop_filter(face_x: float | None, blur_background: bool) -> str:
    """Build the video filter that produces a 1080x1920 frame."""
    if blur_background:
        # full-width video centered over a blurred, scaled copy
        return (
            f"split=2[bg][fg];"
            f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},gblur=sigma=24,eq=brightness=-0.08[bgb];"
            f"[fg]scale={OUT_W}:-2[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
        )
    # 9:16 crop, slid toward the detected face center (clamped inside the frame)
    cx = face_x if face_x is not None else 0.5
    # crop width for 9:16 from source height: ih*9/16; x offset centers on cx
    return (
        f"crop=w='min(iw,ih*9/16)':h=ih:"
        f"x='clip(iw*{cx:.4f}-ih*9/32, 0, iw-min(iw,ih*9/16))':y=0,"
        f"scale={OUT_W}:{OUT_H}"
    )


def _watermark_overlay(position: str) -> str:
    pad = 40
    coords = {
        "top-left": f"{pad}:{int(OUT_H * 0.12)}",
        "top-right": f"W-w-{pad}:{int(OUT_H * 0.12)}",
        "bottom-left": f"{pad}:H-h-{int(OUT_H * 0.16)}",
        "bottom-right": f"W-w-{pad}:H-h-{int(OUT_H * 0.16)}",
        "center": "(W-w)/2:(H-h)/2",
    }
    return coords.get(position, coords["bottom-right"])


def render_base(
    source_path: str,
    out_path: str,
    start: float,
    end: float,
    *,
    blur_background: bool = False,
    progress_cb: Callable[[float, str], None] | None = None,
) -> str:
    """Cut + crop + loudness-normalize into a textless 1080x1920 base clip."""
    if progress_cb:
        progress_cb(0.05, "Detecting speaker position...")
    face_x = None if blur_background else find_face_center_x(source_path, start, end)

    if progress_cb:
        progress_cb(0.2, "Measuring loudness...")
    measured = _measure_loudness(source_path, start, end)

    if progress_cb:
        progress_cb(0.35, "Rendering base clip (crop + audio normalize)...")
    vf = _crop_filter(face_x, blur_background)
    _run_ffmpeg(
        [
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", source_path,
            "-vf", f"{vf},fps={FPS},format=yuv420p",
            "-af", _loudnorm_filter(measured),
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            out_path,
        ],
        "base render",
    )
    if progress_cb:
        progress_cb(0.8, "Base clip rendered")
    return out_path


def render_text_layer(
    base_path: str,
    out_path: str,
    ass_content: str,
    *,
    watermark_path: str | None = None,
    watermark_position: str = "bottom-right",
    progress_cb: Callable[[float, str], None] | None = None,
) -> str:
    """Burn captions/hook (and optional campaign watermark) onto the base clip."""
    settings = get_settings()
    ass_path = Path(out_path).with_suffix(".ass")
    ass_path.write_text(ass_content, encoding="utf-8")

    # ass filter needs escaping for ':' and '\' in paths
    ass_arg = str(ass_path).replace("\\", "/").replace(":", "\\:")

    if progress_cb:
        progress_cb(0.85, "Burning captions...")

    args: list[str] = ["-i", base_path]
    if watermark_path and Path(watermark_path).exists():
        args += ["-i", watermark_path]
        filter_complex = (
            f"[1:v]scale={int(OUT_W * 0.22)}:-1,format=rgba,colorchannelmixer=aa=0.85[wm];"
            f"[0:v][wm]overlay={_watermark_overlay(watermark_position)}[wmv];"
            f"[wmv]ass='{ass_arg}'[v]"
        )
        args += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a"]
    else:
        args += ["-vf", f"ass='{ass_arg}'"]

    args += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        out_path,
    ]
    _run_ffmpeg(args, "caption burn")

    # Enforce TikTok's size ceiling; re-encode smaller if we somehow blew past it
    size_mb = Path(out_path).stat().st_size / (1024 * 1024)
    if size_mb > settings.max_output_mb:
        if progress_cb:
            progress_cb(0.95, f"Output {size_mb:.0f}MB > {settings.max_output_mb}MB, re-encoding smaller...")
        shrunk = str(Path(out_path).with_suffix(".small.mp4"))
        _run_ffmpeg(
            ["-i", out_path, "-c:v", "libx264", "-preset", "medium", "-crf", "26",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", shrunk],
            "size reduction",
        )
        Path(shrunk).replace(out_path)

    if progress_cb:
        progress_cb(1.0, "Clip ready")
    return out_path


def render_clip(
    source_path: str,
    clip_id: int | str,
    start: float,
    end: float,
    words: list[dict[str, Any]],
    hook: str,
    style: dict[str, Any],
    *,
    blur_background: bool = False,
    watermark_path: str | None = None,
    watermark_position: str = "bottom-right",
    reuse_base: str | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> tuple[str, str]:
    """Full render. Returns (final_path, base_path)."""
    settings = get_settings()
    base_path = reuse_base or str(settings.clips_dir / f"clip_{clip_id}_base.mp4")
    final_path = str(settings.clips_dir / f"clip_{clip_id}.mp4")

    if not (reuse_base and Path(base_path).exists()):
        render_base(source_path, base_path, start, end,
                    blur_background=blur_background, progress_cb=progress_cb)

    ass = build_ass(words, start, end, hook, style)
    render_text_layer(
        base_path, final_path, ass,
        watermark_path=watermark_path, watermark_position=watermark_position,
        progress_cb=progress_cb,
    )
    return final_path, base_path
