"""Frames to Video utility runtime.

Converts a folder of image frames into MP4 / WebM / GIF / APNG / WEBP through
the ``engine.ImageToVideo`` FFmpeg wrapper. Mirrors the former built-in runner
but is expressed purely through the InteropContext command set, so the engine
belongs to this utility and no longer lives in the app bridge.
"""

from __future__ import annotations

import os
import traceback

from app.system import get_available_cores
from engine import ImageToVideo

_OUTPUT_EXTENSIONS = {
    "mp4_h264": ".mp4",
    "mp4_av1": ".mp4",
    "webm": ".webm",
    "gif": ".gif",
    "apng": ".apng",
    "webp": ".webp",
}

_CRF_RANGES = {
    "mp4_h264": (0, 51),
    "mp4_av1": (0, 63),
    "webm": (0, 63),
    "webp": (0, 63),
    "gif": (None, None),
    "apng": (None, None),
}


def _clamp_crf(crf, lo, hi):
    try:
        val = int(crf)
    except (ValueError, TypeError):
        return crf
    if lo is not None and hi is not None:
        return max(lo, min(val, hi))
    if hi is not None:
        return min(val, hi)
    if lo is not None:
        return max(val, lo)
    return val


def _check_bitrate(ctx, bitrate_bps, width, height, fps) -> None:
    total_pixels = width * height
    if total_pixels <= 0 or fps <= 0:
        return
    bpp = (bitrate_bps * 1000) / (total_pixels * fps)
    if bpp > 0.3:
        if not ctx.confirm(
            "Bitrate is too high for the given resolution and FPS that may cause the file size to be too "
            "large and issues with playback. Do you want to continue?",
            title="Bitrate too high", yes="Continue", no="Cancel",
        ):
            raise RuntimeError("ABORTED_BY_USER")
    elif bpp < 0.03:
        if not ctx.confirm(
            "Bitrate is too low for the given resolution and FPS that may cause blurry video. "
            "Do you want to continue?",
            title="Bitrate too low", yes="Continue", no="Cancel",
        ):
            raise RuntimeError("ABORTED_BY_USER")


def run(ctx) -> dict:
    source = str(ctx.get("source_folder", "") or "").strip()
    output_folder = str(ctx.get("output_folder", "") or "").strip()
    fmt = str(ctx.get("output_type", "mp4_h264") or "mp4_h264")
    fps = ctx.get("fps", 30)
    crf = ctx.get("crf")
    threads = int(ctx.get("threads", 1) or 1)
    transparent = bool(ctx.get("transparent", False))
    q_mode = str(ctx.get("quality_mode", "CRF") or "CRF").lower()
    bitrate = ctx.get("bitrate")
    bg = str(ctx.get("background", "black") or "black")
    bg_color = ctx.get("background_color")
    open_after = bool(ctx.get("open_explorer_after_conversion", False))
    gif_colors = int(ctx.get("gif_color_limit", 256) or 256)

    if not source:
        ctx.throw_error("Please select a source folder.")
        return {"ok": False, "message": "Missing source folder."}
    if not output_folder:
        ctx.throw_error("Please select an output folder.")
        return {"ok": False, "message": "Missing output folder."}

    try:
        fps_val = float(fps)
        if fps_val <= 0:
            raise ValueError()
    except Exception:
        ctx.throw_error("Please enter a valid FPS value.")
        return {"ok": False, "message": "Invalid FPS value."}

    try:
        total_cores = get_available_cores()
        threads = max(1, min(int(threads), total_cores))
    except Exception:
        threads = 1

    desired_ext = _OUTPUT_EXTENSIONS.get(fmt, ".mp4")
    output = str(ctx.get("output_file", "") or "").strip()
    if not output:
        root_name = os.path.basename(os.path.normpath(source)) or "video"
        output = os.path.join(output_folder, root_name + desired_ext)
    else:
        root, ext = os.path.splitext(output)
        if ext.lower() != desired_ext:
            output = root + desired_ext
            ctx.log(f"Output extension adjusted to '{desired_ext}'.")

    source_mode = str(ctx.get("source_mode", "folder") or "folder").lower()
    if source_mode == "file":
        if not os.path.isfile(source):
            ctx.throw_error(f"The source file '{source}' does not exist.")
            return {"ok": False, "message": "missing source file"}
        frames_dir = os.path.dirname(source) or "."
        ctx.log(f"Using directory of source file: {frames_dir}")
    else:
        if not os.path.isdir(source):
            ctx.throw_error(f"The source folder '{source}' does not exist.")
            return {"ok": False, "message": "missing source folder"}
        frames_dir = source

    try:
        all_files = [f for f in os.listdir(frames_dir) if not f.startswith(".")]
        total_frames = len(all_files)
    except Exception:
        total_frames = None

    out_dir = os.path.dirname(output) or "."
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
            ctx.log(f"Created output folder: {out_dir}")
        except Exception:
            ctx.throw_error(f"The output folder '{out_dir}' could not be created.")
            return {"ok": False, "message": "missing output folder"}
    if os.path.exists(output):
        if not ctx.confirm(
            f"The file '{output}' already exists. Do you want to replace it?",
            title="File Exists Warning", yes="Replace", no="Cancel",
        ):
            ctx.log("Conversion cancelled because the output file already exists.", "warn")
            return {"ok": False, "message": "Cancelled by user."}

    if fmt == "gif":
        gif_colors = max(4, min(gif_colors, 256))
        if fps_val > 50:
            if not ctx.confirm(
                "GIFs with FPS over 50 may be very large and play poorly. Continue anyway?",
                title="High FPS Warning", yes="Continue", no="Cancel",
            ):
                return {"ok": False, "message": "Cancelled by user."}
        if fps_val > 100:
            ctx.log("GIF FPS cannot exceed 100. It will be clamped to 100.", "warn")
            fps_val = 100.0
        if total_frames is not None and total_frames > 300:
            if not ctx.confirm(
                f"GIF with {total_frames} frames may produce a very large file. "
                "Consider using WebM instead. Continue with GIF?",
                title="Many Frames Warning", yes="Continue", no="Cancel",
            ):
                return {"ok": False, "message": "Cancelled by user."}
    if fmt == "apng":
        if fps_val > 50:
            if not ctx.confirm(
                "APNGs with FPS over 50 may be very large and play poorly. Continue anyway?",
                title="High FPS Warning", yes="Continue", no="Cancel",
            ):
                return {"ok": False, "message": "Cancelled by user."}
        if fps_val > 100:
            ctx.log("APNG FPS cannot exceed 100. It will be clamped to 100.", "warn")
            fps_val = 100.0
        if total_frames is not None and total_frames > 100:
            if not ctx.confirm(
                f"APNG with {total_frames} frames may produce a very large file. "
                "Consider using WebM instead. Continue with APNG?",
                title="Many Frames Warning", yes="Continue", no="Cancel",
            ):
                return {"ok": False, "message": "Cancelled by user."}

    crf_int = crf
    lo, hi = _CRF_RANGES.get(fmt, (None, None))
    if crf is not None and fmt in ("mp4_h264", "mp4_av1", "webm", "webp"):
        try:
            crf_int = int(crf)
        except (ValueError, TypeError):
            ctx.throw_error("Please enter a valid integer CRF value.")
            return {"ok": False, "message": "Invalid CRF value."}
        crf_int = _clamp_crf(crf_int, 0, hi)

    if fmt != "webp" and q_mode == "lossless":
        q_mode = "crf"

    bitrate_val = None
    if q_mode in ("bitrate", "2-pass vbr"):
        try:
            bitrate_val = int(bitrate)
            if bitrate_val <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            bitrate_val = 8000
        try:
            w, h = ImageToVideo.get_dimensions_from_first_frame_static(frames_dir)
            _check_bitrate(ctx, bitrate_val, w, h, fps_val)
        except RuntimeError:
            raise
        except Exception as exc:
            ctx.log(f"Could not validate bitrate: {exc}", "warn")

    try:
        if bg == "white":
            bg_color = (255, 255, 255)
        elif bg == "custom" and bg_color:
            bg_color = (int(bg_color[0] or 0), int(bg_color[1] or 0), int(bg_color[2] or 0))
        else:
            bg_color = (0, 0, 0)
    except Exception:
        bg_color = (0, 0, 0)

    ctx.log("Starting conversion...")
    ctx.log(f"Source: {source}")
    ctx.log(f"Output: {output}")
    ctx.log(f"Format: {fmt}")
    ctx.log(f"FPS: {fps_val}")
    if crf_int is not None and q_mode != "lossless":
        ctx.log(f"CRF: {crf_int}")
    ctx.log(f"Threads: {threads}")

    ctx.status("Checking FFmpeg...", "blue")
    try:
        ImageToVideo.ffmpeg_checker()
        ctx.log("FFmpeg check passed.")
    except Exception as exc:
        ctx.status("FFmpeg is missing", "red")
        ctx.throw_error(f"FFmpeg not found: {exc}")
        return {"ok": False, "message": "FFmpeg not found.", "reason": str(exc)}

    ctx.status("Converting video...", "blue")
    try:
        ImageToVideo.frames_to_video(
            frames_dir, output, fmt, transparent, float(fps_val), crf_int,
            progress_callback=lambda pct: ctx.progress(pct, f"Converting frames to video... {pct}%"),
            amount_threads=threads,
            abort_event=ctx.abort_event,
            pause_event=ctx.pause_event,
            gif_max_colors=gif_colors if fmt == "gif" else None,
            apng_transparent=transparent,
            gif_transparent=transparent,
            webp_transparent=transparent,
            background_color=bg_color,
            quality_mode=q_mode,
            bitrate=bitrate_val,
        )
        if ctx.abort_event.is_set():
            ctx.log("Conversion aborted by user.", "warn")
            return {"ok": False, "message": "Aborted by user."}
        ctx.progress(100, "Video converted successfully!")
        ctx.status("Video converted successfully!", "green")
        ctx.log("Conversion completed successfully!")
        if open_after:
            ctx.open_explorer(output)
            ctx.log(f"Opened file explorer: {os.path.dirname(output)}")
        return {"ok": True, "message": "Video has been converted successfully!"}
    except Exception as exc:
        ctx.log("ERROR: Conversion failed!", "error")
        if "ABORTED_BY_USER" in str(exc):
            ctx.log("Conversion aborted by user.", "warn")
            return {"ok": False, "message": "Aborted by user."}
        ctx.log(traceback.format_exc(), "error")
        ctx.status("Error occurred during conversion", "red")
        return {"ok": False, "message": "Conversion failed.", "reason": str(exc)}