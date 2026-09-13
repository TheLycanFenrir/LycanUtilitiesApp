"""Generate production-ready texture mipmap chains with Pillow and optional NumPy.

Normal-map normalization is chunked so its temporary NumPy arrays are bounded by a
configurable number of rows instead of the full texture height.
"""

from __future__ import annotations

from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock
from typing import Callable, Iterator, Literal, Optional
import time

from PIL import Image


ResampleFilter = Literal["lanczos", "box", "mitchell", "bilinear"]
NPOTMode = Literal["none", "pad_edge", "stretch"]
ImageFormat = Literal["png", "jpg", "jpeg", "webp", "tga", "tiff"]
MipCallback = Callable[["MipStatus"], None]


@dataclass(frozen=True)
class MipStatus:
    """Progress event emitted after a level is generated or exported."""

    event: str
    level: int
    size: tuple[int, int]
    message: str


@dataclass(frozen=True)
class TextureExportSettings:
    """Image-format settings shared by individual mip exports and DDS fallback."""

    image_format: ImageFormat = "png"
    quality: int = 95
    png_compress_level: int = 6
    png_optimize: bool = False
    jpeg_progressive: bool = False
    jpeg_subsampling: Literal["4:4:4", "4:2:0"] = "4:2:0"
    webp_lossless: bool = False
    retain_alpha: bool = True
    alpha_background: tuple[int, int, int] = (0, 0, 0)
    # Compression options surfaced by the UI for TGA/TIFF
    tga_compression: Literal["none", "rle"] = "none"
    tiff_compression: Literal["none", "lzw", "zip", "jpeg"] = "none"

    def __post_init__(self) -> None:
        if self.image_format.lower() not in {"png", "jpg", "jpeg", "webp", "tga", "tiff"}:
            raise ValueError(f"Unsupported image format: {self.image_format!r}")
        if not 1 <= self.quality <= 100:
            raise ValueError("quality must be in the range 1..100.")
        if not 0 <= self.png_compress_level <= 9:
            raise ValueError("png_compress_level must be in the range 0..9.")
        if self.tga_compression not in {"none", "rle"}:
            raise ValueError("tga_compression must be either 'none' or 'rle'.")
        if self.tiff_compression not in {"none", "lzw", "zip", "jpeg"}:
            raise ValueError("tiff_compression must be one of 'none','lzw','zip','jpeg'.")

    @property
    def extension(self) -> str:
        return "jpg" if self.image_format.lower() == "jpeg" else self.image_format.lower()


@dataclass(frozen=True)
class MipExportResult:
    """Paths written by an export operation and whether a DDS container was produced."""

    paths: tuple[Path, ...]
    dds_path: Optional[Path] = None


class TextureMipMapGenerator:
    """Thread-safe mipmap generator for color and normal-map texture pipelines.

    ``callback_executor`` lets a GUI enqueue callback work without blocking the
    encode loop.  The generator has no shared image cache, so independent instances
    can safely run on different worker threads.
    """

    _FILTERS = {
        "lanczos": Image.Resampling.LANCZOS,
        "box": Image.Resampling.BOX,
        # Pillow's high-quality cubic filter is the portable Mitchell/Cubic option.
        "mitchell": Image.Resampling.BICUBIC,
        "bilinear": Image.Resampling.BILINEAR,
    }

    def __init__(self, callback: Optional[MipCallback] = None,
                 callback_executor: Optional[Executor] = None,
                 normalization_chunk_rows: int = 512,
                 abort_event: Optional[Event] = None,
                 pause_event: Optional[Event] = None) -> None:
        if normalization_chunk_rows <= 0:
            raise ValueError("normalization_chunk_rows must be positive.")
        self._callback = callback
        self._callback_executor = callback_executor
        self._normalization_chunk_rows = normalization_chunk_rows
        self._abort_event = abort_event
        self._pause_event = pause_event
        self._lock = RLock()

    def _check_abort(self) -> bool:
        """Return True when a cancellation has been requested."""
        return self._abort_event is not None and self._abort_event.is_set()

    def _wait_if_paused(self) -> None:
        """Block while the job is paused; abort is honoured while paused."""
        while self._pause_event is not None and self._pause_event.is_set():
            if self._check_abort():
                raise RuntimeError("ABORTED_BY_USER")
            time.sleep(0.1)

    def _emit(self, status: MipStatus) -> None:
        if self._callback is None:
            return
        if self._callback_executor is not None:
            self._callback_executor.submit(self._callback, status)
        else:
            self._callback(status)

    @staticmethod
    def _load(source: str | Path) -> tuple[Image.Image, Optional[bytes]]:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Texture not found: {path}")
        with Image.open(path) as opened:
            opened.load()
            return opened.copy(), opened.info.get("icc_profile")

    @staticmethod
    def _next_power_of_two(value: int) -> int:
        return 1 if value <= 1 else 1 << (value - 1).bit_length()

    @staticmethod
    def _nearest_power_of_two(value: int) -> int:
        upper = TextureMipMapGenerator._next_power_of_two(value)
        lower = upper >> 1
        return upper if value - lower >= upper - value else lower

    @staticmethod
    def _edge_pad(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        """Right/bottom edge bleed, keeping the original texels unchanged."""
        target_width, target_height = target_size
        if image.size == target_size:
            return image
        canvas = Image.new(image.mode, target_size)
        width, height = image.size
        canvas.paste(image, (0, 0))
        if target_width > width:
            right_edge = image.crop((width - 1, 0, width, height))
            canvas.paste(right_edge.resize((target_width - width, height)), (width, 0))
        if target_height > height:
            bottom_edge = canvas.crop((0, height - 1, target_width, height))
            canvas.paste(bottom_edge.resize((target_width, target_height - height)), (0, height))
        return canvas

    def _prepare_base(self, image: Image.Image, npot_mode: NPOTMode,
                      resample_filter: ResampleFilter) -> Image.Image:
        if npot_mode not in {"none", "pad_edge", "stretch"}:
            raise ValueError(f"Unsupported NPOT mode: {npot_mode!r}")
        if resample_filter not in self._FILTERS:
            raise ValueError(f"Unsupported resampling filter: {resample_filter!r}")
        if npot_mode == "none":
            return image
        width, height = image.size
        target = ((self._next_power_of_two(width), self._next_power_of_two(height))
                  if npot_mode == "pad_edge"
                  else (self._nearest_power_of_two(width), self._nearest_power_of_two(height)))
        if target == image.size:
            return image
        if npot_mode == "pad_edge":
            return self._edge_pad(image, target)
        return image.resize(target, self._FILTERS[resample_filter])

    def _normalize_normal_map(self, image: Image.Image) -> Image.Image:
        """Renormalize RGB normal vectors in bounded-height NumPy strips.

        The conversion maps RGB from [0, 255] to [-1, 1], divides by vector length
        (with +Z used for zero-length vectors), then maps back to [0, 255]. Alpha is
        copied unchanged.
        """
        try:
            import numpy as np
        except ImportError as error:
            raise RuntimeError("Normal-map mode requires NumPy. Install it with 'pip install numpy'.") from error
        source = image if image.mode == "RGBA" else image.convert("RGBA")
        owns_source = source is not image
        normalized = Image.new("RGBA", source.size)
        for top in range(0, source.height, self._normalization_chunk_rows):
            bottom = min(source.height, top + self._normalization_chunk_rows)
            strip = source.crop((0, top, source.width, bottom))
            try:
                pixels = np.asarray(strip, dtype=np.uint8)
                vectors = pixels[..., :3].astype(np.float32) / 127.5 - 1.0
                lengths = np.linalg.norm(vectors, axis=2, keepdims=True)
                vectors = np.divide(vectors, lengths, out=np.zeros_like(vectors), where=lengths > 1e-8)
                vectors[lengths[..., 0] <= 1e-8] = (0.0, 0.0, 1.0)
                output = np.empty_like(pixels)
                output[..., :3] = np.clip((vectors + 1.0) * 127.5 + 0.5, 0, 255).astype(np.uint8)
                output[..., 3] = pixels[..., 3]
                normalized.paste(Image.fromarray(output, "RGBA"), (0, top))
            finally:
                strip.close()
        if owns_source:
            source.close()
        return normalized

    def iter_mipmaps(self, source: str | Path, *, normal_map: bool = False,
                     npot_mode: NPOTMode = "none",
                     resample_filter: ResampleFilter = "lanczos") -> Iterator[tuple[int, Image.Image]]:
        """Yield level-0 through 1×1 while retaining only the current image internally.

        Consumers that need the full chain in memory can use :meth:`generate_chain`.
        Streaming this iterator directly into :meth:`export` is preferred for 4K+.
        """
        with self._lock:
            image, _ = self._load(source)
            current = self._prepare_base(image, npot_mode, resample_filter)
            if current is not image:
                image.close()
            if normal_map:
                renormalized = self._normalize_normal_map(current)
                current.close()
                current = renormalized
        level = 0
        try:
            while True:
                self._wait_if_paused()
                self._emit(MipStatus("level_generated", level, current.size,
                                     f"Generated mip level {level}: {current.width}×{current.height}"))
                yield level, current
                if current.size == (1, 1):
                    break
                next_size = (max(1, current.width // 2), max(1, current.height // 2))
                next_image = current.resize(next_size, self._FILTERS[resample_filter])
                if normal_map:
                    normalized = self._normalize_normal_map(next_image)
                    next_image.close()
                    next_image = normalized
                current.close()
                current = next_image
                level += 1
        finally:
            current.close()

    def generate_chain(self, source: str | Path, *, normal_map: bool = False,
                       npot_mode: NPOTMode = "none",
                       resample_filter: ResampleFilter = "lanczos") -> list[Image.Image]:
        """Return a copied full mip chain. Prefer :meth:`export` for huge textures."""
        chain: list[Image.Image] = []
        for _, level in self.iter_mipmaps(source, normal_map=normal_map, npot_mode=npot_mode,
                                          resample_filter=resample_filter):
            chain.append(level.copy())
        return chain

    @staticmethod
    def _save(image: Image.Image, path: Path, settings: TextureExportSettings,
              icc_profile: Optional[bytes]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = settings.image_format.upper().replace("JPG", "JPEG")
        save_image = image
        options: dict[str, object] = {"icc_profile": icc_profile} if icc_profile else {}
        if fmt == "JPEG":
            if image.mode in {"RGBA", "LA"}:
                alpha = image.getchannel("A")
                background = Image.new("RGB", image.size, settings.alpha_background)
                background.paste(image.convert("RGB"), mask=alpha)
                save_image = background
            elif image.mode != "RGB":
                save_image = image.convert("RGB")
            options.update(quality=settings.quality, progressive=settings.jpeg_progressive,
                           subsampling=0 if settings.jpeg_subsampling == "4:4:4" else 2)
        elif fmt == "PNG":
            if not settings.retain_alpha and "A" in image.getbands():
                save_image = image.convert("RGB")
            options.update(compress_level=settings.png_compress_level, optimize=settings.png_optimize)
        elif fmt == "WEBP":
            if not settings.retain_alpha and "A" in image.getbands():
                save_image = image.convert("RGB")
            options.update(quality=settings.quality, lossless=settings.webp_lossless)
        save_image.save(path, format=fmt, **options)

    @staticmethod
    def _mip_name(template: str, texture_name: str, level: int, extension: str) -> str:
        try:
            filename = template.format(texture_name=texture_name, basename=texture_name,
                                       level=level, ext=extension)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Invalid naming template: {template!r}") from error
        if not filename:
            raise ValueError("The naming template produced an empty filename.")
        return filename

    def export(self, source: str | Path, output_directory: str | Path, *,
               normal_map: bool = False, npot_mode: NPOTMode = "none",
               resample_filter: ResampleFilter = "lanczos",
               export: TextureExportSettings = TextureExportSettings(),
               naming_template: str = "{texture_name}_mip{level}.{ext}",
               export_dds: bool = False) -> MipExportResult:
        """Stream mip levels to individual files, optionally attempting a DDS container.

        DDS is attempted through ``imageio.v3`` only when requested and available.
        Any unavailable plugin/unsupported DDS writer cleanly falls back to the
        individual image files already written.
        """
        source_path = Path(source)
        output_path = Path(output_directory)
        with Image.open(source_path) as opened:
            icc_profile = opened.info.get("icc_profile")
        written: list[Path] = []
        dds_arrays: list[object] = []
        for level, image in self.iter_mipmaps(source, normal_map=normal_map, npot_mode=npot_mode,
                                               resample_filter=resample_filter):
            if self._check_abort():
                raise RuntimeError("ABORTED_BY_USER")
            self._wait_if_paused()
            filename = self._mip_name(naming_template, source_path.stem, level, export.extension)
            path = output_path / filename
            self._save(image, path, export, icc_profile)
            written.append(path)
            if export_dds:
                try:
                    import numpy as np
                    dds_image = image.convert("RGBA" if export.retain_alpha else "RGB")
                    try:
                        dds_arrays.append(np.asarray(dds_image).copy())
                    finally:
                        dds_image.close()
                except ImportError:
                    export_dds = False
                    self._emit(MipStatus("dds_fallback", level, image.size,
                                         "DDS export skipped because NumPy/imageio is unavailable."))
            self._emit(MipStatus("level_saved", level, image.size, f"Saved {path.name}"))

        dds_path: Optional[Path] = None
        if export_dds:
            candidate = output_path / f"{source_path.stem}.dds"
            try:
                import imageio.v3 as imageio
                candidate.parent.mkdir(parents=True, exist_ok=True)
                imageio.imwrite(candidate, dds_arrays, extension=".dds")
                dds_path = candidate
            except Exception as error:
                candidate.unlink(missing_ok=True)
                self._emit(MipStatus("dds_fallback", 0, (0, 0),
                                     f"DDS export unavailable; wrote individual mips instead ({error})."))
        return MipExportResult(tuple(written), dds_path)