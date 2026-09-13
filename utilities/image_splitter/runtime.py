"""Image Splitter utility runtime.

Splits source images into grids, fixed-size tiles or alpha components using the
``engine.ImageSplitter`` engine. Expresses the former built-in runner through
the InteropContext command set only.
"""

from __future__ import annotations

import os
import traceback

from concurrent.futures import ThreadPoolExecutor

from engine import (
    ImageSplitter,
    ExportSettings as ImageExportSettings,
    SplitStatus,
    SplitAbortedError,
)

_GRID_FALLBACK = "{basename}_r{row}_c{col}.{ext}"
_ALPHA_FALLBACK = "{basename}_tile_{index}.{ext}"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tga", ".tiff", ".bmp")


def _split_status(ctx, status: SplitStatus) -> None:
    event = str(status.event).lower()
    if event in {"warning", "error", "aborted", "completed", "complete", "finished", "failed"}:
        msg = f"[{status.event}] {status.message}"
        if status.total:
            msg += f" ({status.completed}/{status.total})"
        ctx.log(msg, "error" if event == "error"
                 else ("warn" if event in {"warning", "aborted", "failed"} else "info"))
        if status.total:
            ctx.progress(status.completed / status.total * 100)
    elif status.total:
        ctx.progress(status.completed / status.total * 100)


def _to_int(ctx, key: str, default: int, lo: int | None, hi: int | None) -> int:
    try:
        val = int(ctx.get(key, default) or default)
    except (ValueError, TypeError):
        val = default
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


def run(ctx) -> dict:
    source = str(ctx.get("source", "") or "").strip()
    out = str(ctx.get("output", "") or "").strip()
    mode = str(ctx.get("mode", "grid") or "grid")
    fmt = str(ctx.get("image_format", "png") or "png").lower()
    source_mode = str(ctx.get("source_mode", "single") or "single")

    if not source or not out:
        ctx.throw_error("Source and output must be set.")
        return {"ok": False, "message": "Missing source or output."}

    quality = _to_int(ctx, "quality", 95, 1, 100)
    compress_level = _to_int(ctx, "png_compress_level", 6, 0, 9)
    bleed_radius = _to_int(ctx, "bleed_radius", 0, 0, None)

    export = ImageExportSettings(
        image_format=fmt,
        quality=quality,
        png_compress_level=compress_level,
        discard_blank_tiles=bool(ctx.get("discard_blank_tiles", False)),
        tga_compression=str(ctx.get("tga_compression", "none") or "none"),
        tiff_compression=str(ctx.get("tiff_compression", "none") or "none"),
        bleed_radius=bleed_radius,
    )

    save_executor = ThreadPoolExecutor(max_workers=4)
    splitter = ImageSplitter(
        callback=lambda status: _split_status(ctx, status),
        callback_executor=None,
        abort_event=ctx.abort_event,
        pause_event=ctx.pause_event,
        save_executor=save_executor,
        confirm_callback=lambda msg: ctx.confirm(
            msg, title="File Count Warning", yes="Proceed", no="Cancel",
        ),
    )

    def run_file(path: str) -> None:
        naming = str(ctx.get("naming_template", "") or "").strip()
        if mode == "grid":
            rows = _to_int(ctx, "rows", 1, 1, None)
            cols = _to_int(ctx, "columns", 1, 1, None)
            res_mode = str(ctx.get("resolution_mode", "allow_variation") or "allow_variation")
            pad_mode = str(ctx.get("padding_mode", "edge") or "edge")
            splitter.split_grid(
                path, out, rows, cols,
                resolution_mode=res_mode, padding_mode=pad_mode,
                export=export,
                naming_template=naming or _GRID_FALLBACK,
            )
        elif mode == "tile_size":
            tw = _to_int(ctx, "tile_width", 512, 1, None)
            th = _to_int(ctx, "tile_height", 512, 1, None)
            res_mode = str(ctx.get("resolution_mode", "allow_variation") or "allow_variation")
            pad_mode = str(ctx.get("padding_mode", "edge") or "edge")
            splitter.split_dimensions(
                path, out, tw, th,
                resolution_mode=res_mode, padding_mode=pad_mode,
                export=export,
                naming_template=naming or _GRID_FALLBACK,
            )
        else:
            alpha = _to_int(ctx, "alpha_threshold", 0, 0, 255)
            splitter.split_transparent_components(
                path, out, alpha_threshold=alpha,
                export=export,
                naming_template=naming or _ALPHA_FALLBACK,
            )

    try:
        if source_mode == "bulk":
            if not os.path.isdir(source):
                ctx.throw_error(f"Error: Source folder does not exist: {source}")
                return {"ok": False, "message": "Source folder does not exist.", "reason": "missing source folder"}
            image_files = [f for f in os.listdir(source) if f.lower().endswith(_IMAGE_EXTS)]
            if not image_files:
                ctx.throw_error("Error: No image files found in source folder")
                return {"ok": False, "message": "No image files found.", "reason": "no image files"}
            ctx.log(f"Found {len(image_files)} images to process")
            for idx, img_file in enumerate(image_files, 1):
                ctx.wait_if_paused()
                if ctx.abort_event.is_set():
                    ctx.log("Abort requested; stopping bulk processing.", "warn")
                    break
                img_path = os.path.join(source, img_file)
                ctx.log(f"Processing {idx}/{len(image_files)}: {img_file}")
                try:
                    run_file(img_path)
                    ctx.log(f"Completed {idx}/{len(image_files)}: {img_file}")
                except SplitAbortedError:
                    raise
                except Exception as exc:
                    ctx.log(f"Error processing {img_file}: {exc}", "error")
                    ctx.log(traceback.format_exc(), "error")
            ctx.log(f"Bulk split complete. Processed {len(image_files)} images.")
        else:
            if not os.path.isfile(source):
                ctx.throw_error(f"Error: Source file does not exist: {source}")
                return {"ok": False, "message": "Source file does not exist.", "reason": "missing source file"}
            ctx.log("Starting split...")
            run_file(source)
            ctx.log("Split complete.")

        if ctx.abort_event.is_set():
            ctx.log("Split operation aborted by user.", "warn")
            ctx.status("Split operation aborted by user.", "orange")
            return {"ok": False, "message": "Aborted by user."}
        ctx.progress(100, "Split complete!")
        if ctx.get("open_explorer_after_conversion", False):
            ctx.open_explorer(out)
        ctx.status("Split completed successfully!", "green")
        return {"ok": True, "message": "Split completed successfully!"}
    except SplitAbortedError as exc:
        if ctx.abort_event.is_set():
            ctx.status("Split aborted.", "orange")
            return {"ok": False, "message": "Aborted by user."}
        ctx.log(f"Split aborted: {exc}", "warn")
        ctx.status("Split aborted.", "orange")
        return {"ok": False, "message": "Split aborted.", "reason": str(exc)}
    except Exception as exc:
        ctx.log(f"Error: {exc}", "error")
        ctx.log(traceback.format_exc(), "error")
        if ctx.abort_event.is_set():
            ctx.log("Split operation aborted by user.", "warn")
            ctx.status("Split operation aborted by user.", "orange")
            return {"ok": False, "message": "Aborted by user."}
        ctx.status("Split failed.", "red")
        return {"ok": False, "message": "Split failed.", "reason": str(exc)}
    finally:
        try:
            if ctx.abort_event.is_set():
                save_executor.shutdown(wait=False, cancel_futures=True)
            else:
                save_executor.shutdown(wait=True)
        except Exception:
            pass