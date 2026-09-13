"""Texture Mipmap Generator utility runtime.

Generates mip chains (and optionally a DDS container) from a source texture via
the ``engine.TextureMipMapGenerator`` engine. Mirrors the former built-in runner
through the InteropContext command set only.
"""

from __future__ import annotations

import os
import traceback

from engine import (
    TextureMipMapGenerator,
    TextureExportSettings,
    MipStatus,
)

_DEFAULT_TEMPLATE = "{texture_name}_mip{level}.{ext}"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tga", ".tiff", ".bmp")


def _mip_status(ctx, status: MipStatus) -> None:
    event = str(status.event).lower()
    if event in {"level_saved", "level_generated"}:
        ctx.log(f"[{status.event}] Level {status.level}: {status.message} Size={status.size[0]}x{status.size[1]}")
    elif event == "dds_fallback":
        ctx.log(f"[{status.event}] {status.message}", "warn")
    else:
        ctx.log(repr(status))


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
    source_mode = str(ctx.get("source_mode", "single") or "single")

    if not source or not out:
        ctx.throw_error("Source and output must be set.")
        return {"ok": False, "message": "Missing source or output."}

    fmt = str(ctx.get("image_format", "png") or "png").lower()
    quality = _to_int(ctx, "quality", 95, 1, 100)
    compress_level = _to_int(ctx, "png_compress_level", 6, 0, 9)

    export = TextureExportSettings(
        image_format=fmt,
        quality=quality,
        png_compress_level=compress_level,
        retain_alpha=bool(ctx.get("retain_alpha", True)),
        tga_compression=str(ctx.get("tga_compression", "none") or "none"),
        tiff_compression=str(ctx.get("tiff_compression", "none") or "none"),
    )

    gen = TextureMipMapGenerator(
        callback=lambda st: _mip_status(ctx, st),
        abort_event=ctx.abort_event,
        pause_event=ctx.pause_event,
    )
    naming = str(ctx.get("naming_template", "") or "").strip() or _DEFAULT_TEMPLATE
    normal_map = bool(ctx.get("normal_map", False))
    npot_mode = str(ctx.get("npot_mode", "none") or "none")
    res_filter = str(ctx.get("resample_filter", "lanczos") or "lanczos")
    export_dds = bool(ctx.get("export_dds", False))

    def run_file(path: str) -> None:
        gen.export(
            path, out,
            normal_map=normal_map, npot_mode=npot_mode,
            resample_filter=res_filter, export=export,
            naming_template=naming, export_dds=export_dds,
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
            ctx.log(f"Found {len(image_files)} textures to process")
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
                except Exception as exc:
                    ctx.log(f"Error processing {img_file}: {exc}", "error")
                    ctx.log(traceback.format_exc(), "error")
            ctx.log(f"Bulk mipmap generation complete. Processed {len(image_files)} textures.")
        else:
            if not os.path.isfile(source):
                ctx.throw_error(f"Error: Source file does not exist: {source}")
                return {"ok": False, "message": "Source file does not exist.", "reason": "missing source file"}
            ctx.log("Starting mipmap generation...")
            run_file(source)
            ctx.log("Mipmap generation complete.")

        if ctx.abort_event.is_set():
            ctx.log("Mipmap generation aborted by user.", "warn")
            ctx.status("Mipmap generation aborted by user.", "orange")
            return {"ok": False, "message": "Aborted by user."}
        ctx.progress(100, "Mipmap generation complete!")
        if ctx.get("open_explorer_after_conversion", False):
            ctx.open_explorer(out)
        ctx.status("Mipmaps generated successfully!", "green")
        return {"ok": True, "message": "Mipmap generation completed successfully!"}
    except Exception as exc:
        if ctx.abort_event.is_set() or "ABORTED_BY_USER" in str(exc):
            ctx.log("Mipmap generation aborted by user.", "warn")
            ctx.status("Mipmap generation aborted by user.", "orange")
            return {"ok": False, "message": "Aborted by user."}
        ctx.log(f"Error: {exc}", "error")
        ctx.log(traceback.format_exc(), "error")
        ctx.status("Mipmap generation failed.", "red")
        return {"ok": False, "message": "Mipmap generation failed.", "reason": str(exc)}