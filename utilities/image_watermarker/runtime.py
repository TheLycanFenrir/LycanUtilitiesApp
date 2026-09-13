"""Image Watermarker runtime - reference implementation of the mod contract.

The Core Execution Engine imports this module and calls ``run(ctx)`` with an
``InteropContext`` exposing the cross-language command set (get_form_data,
execute_command, send_log_output, throw_error, ...). The runtime never talks to
the UI directly; it only dips into ``ctx``.
"""

import ast
import datetime
import os

from PIL import Image, ImageDraw, ImageFont

_ANCHORS = {
    "top_left": ("tl", (16, 16)),
    "top_center": ("tc", (0, 16)),
    "top_right": ("tr", (-16, 16)),
    "middle_left": ("ml", (16, 0)),
    "center": ("mm", (0, 0)),
    "middle_right": ("mr", (-16, 0)),
    "bottom_left": ("bl", (16, -16)),
    "bottom_center": ("bc", (0, -16)),
    "bottom_right": ("br", (-16, -16)),
}


def _load_font(px: int) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=px)
            except Exception:
                continue
    return ImageFont.load_default()


def _resolve_position(anchor: str, w: int, h: int, pad_x: int, pad_y: int, text_w: int, text_h: int):
    key = _ANCHORS.get(str(anchor).lower().replace(" ", "_"), _ANCHORS["bottom_right"])
    mode, (dx, dy) = key
    x = 0
    y = 0
    if "l" in mode:
        x = pad_x
    elif "r" in mode:
        x = w - pad_x - text_w
    else:
        x = (w - text_w) // 2
    if "t" in mode:
        y = pad_y
    elif "b" in mode:
        y = h - pad_y - text_h
    else:
        y = (h - text_h) // 2
    return x + dx, y + dy


def _parse_color(value):
    """Accept [r, g, b] lists or their persisted string form ``"[r, g, b]"``."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [int(value[0]), int(value[1]), int(value[2])]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [255, 255, 255]
        if isinstance(parsed, (list, tuple)) and len(parsed) >= 3:
            return [int(parsed[0]), int(parsed[1]), int(parsed[2])]
    return [255, 255, 255]


def run(ctx) -> dict:
    source = str(ctx.get("input_image") or "").strip()
    output = str(ctx.get("output_image") or "").strip()
    text = str(ctx.get("watermark_text") or "").strip()
    include_date = bool(ctx.get("date_stamp", True))
    color = _parse_color(ctx.get("watermark_color"))
    alpha = int(ctx.get("watermark_alpha", 40) or 40)
    size = int(ctx.get("font_size", 0) or 0)
    position = str(ctx.get("watermark_position") or "bottom_right")

    if not source or not os.path.isfile(source):
        ctx.throw_error("Source image does not exist: " + source)
        return {"ok": False, "message": "Missing source image."}
    if not output:
        ctx.throw_error("Select an output image path first.")
        return {"ok": False, "message": "Missing output image."}

    if include_date:
        text = f"{text}  {datetime.date.today().isoformat()}".strip()
    if not text:
        ctx.throw_error("Watermark text is empty.")
        return {"ok": False, "message": "Empty watermark text."}

    try:
        image = Image.open(source).convert("RGBA")
    except Exception as exc:
        ctx.throw_error(f"Could not open source image: {exc}")
        return {"ok": False, "message": str(exc)}

    width, height = image.size
    ctx.progress(15, "Rendering watermark...")
    alpha = max(0, min(100, alpha))
    font_px = size if size and size > 0 else max(12, int(width * 0.055))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _load_font(font_px)
    r, g, b = (int(color[0]), int(color[1]), int(color[2])) if len(color) >= 3 else (255, 255, 255)
    fill = (r, g, b, int(round(alpha * 255 / 100)))

    try:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=2)
    except Exception:
        bbox = draw.textbbox((0, 0), text, font=font)

    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = _resolve_position(position, width, height, 20, 20, text_w, text_h)
    try:
        draw.text((x, y), text, font=font, fill=fill, stroke_width=2, stroke_fill=(0, 0, 0, alpha))
    except Exception:
        draw.text((x, y), text, font=font, fill=fill)
    image = Image.alpha_composite(image, overlay)

    ctx.progress(70, "Saving image...")
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    try:
        image.convert("RGB").save(output)
    except Exception as exc:
        ctx.throw_error(f"Could not save output image: {exc}")
        return {"ok": False, "message": str(exc)}

    ctx.progress(100, "Done")
    return {"ok": True, "message": f"Saved watermarked image to {output}"}