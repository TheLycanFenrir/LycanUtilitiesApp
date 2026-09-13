"""Production-oriented image grid, pixel-size, and alpha-component splitter.

The module keeps images in Pillow form and writes one tile at a time, which avoids
retaining a second full image-sized buffer during export.  NumPy/OpenCV are optional;
NumPy is required only for connected-component alpha detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import Executor
from threading import RLock, Event
from typing import Callable, Literal, Optional, Sequence
import time

from PIL import Image

import concurrent.futures as _cf


ResolutionMode = Literal["allow_variation", "bleed_padding", "crop_to_fit", "abort"]
PaddingMode = Literal["edge", "reflect", "texture_bleed"]
ImageFormat = Literal["png", "jpg", "jpeg", "webp", "tga", "tiff"]
StatusCallback = Callable[["SplitStatus"], None]
ConfirmationCallback = Callable[[str], bool]

MODE_ALLOW_VARIATION: ResolutionMode = "allow_variation"
MODE_BLEED_PADDING: ResolutionMode = "bleed_padding"
MODE_CROP_TO_FIT: ResolutionMode = "crop_to_fit"
MODE_ABORT: ResolutionMode = "abort"


class SplitAbortedError(RuntimeError):
    """Raised when a split is intentionally cancelled by ``MODE_ABORT``."""


@dataclass(frozen=True)
class SplitStatus:
    """Structured progress/warning event suitable for GUI and CLI consumers."""

    event: str
    message: str
    completed: int = 0
    total: int = 0
    image_size: tuple[int, int] = (0, 0)
    grid_size: tuple[int, int] = (0, 0)
    remainder: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class ExportSettings:
    """Per-format image export controls.

    Alpha is automatically flattened against ``alpha_background`` for JPEG because
    JPEG has no alpha channel.  ICC profiles are retained when Pillow exposes one.
    """

    image_format: ImageFormat = "png"
    quality: int = 95
    png_compress_level: int = 6
    png_optimize: bool = False
    jpeg_progressive: bool = False
    jpeg_subsampling: Literal["4:4:4", "4:2:0"] = "4:2:0"
    webp_lossless: bool = False
    alpha_background: tuple[int, int, int] = (0, 0, 0)
    discard_blank_tiles: bool = False
    # Compression options for TGA/TIFF exports (UI may surface these choices)
    tga_compression: Literal["none", "rle"] = "none"
    tiff_compression: Literal["none", "lzw", "zip", "jpeg"] = "none"
    # Texture bleed settings for seamless tiling
    bleed_radius: int = 0

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
class Tile:
    """Metadata for one exported crop in source/canvas pixel coordinates."""

    index: int
    row: int
    column: int
    box: tuple[int, int, int, int]
    path: Path
    tile_size: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class SplitResult:
    """Export result including the canvas used to generate the tiles."""

    tiles: tuple[Tile, ...]
    canvas_size: tuple[int, int]
    original_size: tuple[int, int]


class ImageSplitter:
    """Thread-safe splitter with grid, pixel-dimension, and alpha-component modes.

    Instances contain no mutable image cache.  A callback executor can be supplied
    for non-blocking GUI integration; callbacks are otherwise invoked directly after
    each tile is saved and never while the internal lock is held.
    """

    # Safety threshold for file count warnings
    DEFAULT_FILE_COUNT_WARNING_THRESHOLD = 1000

    def __init__(self, callback: Optional[StatusCallback] = None,
                 callback_executor: Optional[Executor] = None,
                 abort_event: Optional[Event] = None,
                 pause_event: Optional[Event] = None,
                 save_executor: Optional[Executor] = None,
                 confirm_callback: Optional[ConfirmationCallback] = None,
                 file_count_warning_threshold: int = DEFAULT_FILE_COUNT_WARNING_THRESHOLD) -> None:
        self._callback = callback
        self._callback_executor = callback_executor
        self._lock = RLock()
        self._abort_event = abort_event
        self._pause_event = pause_event
        self._save_executor = save_executor
        self._confirm_callback = confirm_callback
        self._file_count_warning_threshold = file_count_warning_threshold

    def _emit(self, status: SplitStatus) -> None:
        if self._callback is None:
            return
        if self._callback_executor is not None:
            self._callback_executor.submit(self._callback, status)
        else:
            self._callback(status)

    def _check_abort(self) -> bool:
        """Check whether an abort has been requested."""
        return self._abort_event is not None and self._abort_event.is_set()

    def _wait_if_paused(self) -> None:
        """Block while the job is paused; abort is honoured while paused."""
        while self._pause_event is not None and self._pause_event.is_set():
            if self._check_abort():
                raise SplitAbortedError("Aborted while paused.")
            time.sleep(0.1)

    def _emit_aborted(self) -> None:
        """Emit the aborted status event once."""
        self._emit(
            SplitStatus(
                "aborted",
                "Split operation cancelled by user."
            )
        )

    def _confirm_warning(self, message: str) -> None:
        """Ask for confirmation after a file-count warning; abort if declined."""
        if self._confirm_callback is not None and not self._confirm_callback(message):
            if self._abort_event is not None:
                self._abort_event.set()
            self._emit_aborted()
            raise SplitAbortedError(message)

    def _validate_file_count(self, estimated_count: int) -> tuple[bool, str]:
        """Validate estimated file count against safety thresholds.
        
        Returns:
            tuple[bool, str]: (should_proceed, warning_message)
            If should_proceed is False, the operation should be aborted.
        """
        if estimated_count >= self._file_count_warning_threshold:
            return True, f"Warning: Estimated file count ({estimated_count}) exceeds warning threshold ({self._file_count_warning_threshold}). This may cause performance issues when opening the output directory."
        
        return True, ""

    @staticmethod
    def _axis_sizes(length: int, count: int, mode: ResolutionMode) -> tuple[list[int], int]:
        if count <= 0:
            raise ValueError("Grid rows and columns must be positive.")
        base, remainder = divmod(length, count)
        if base == 0:
            raise ValueError("A grid dimension cannot exceed the corresponding image dimension.")
        if mode == MODE_ABORT and remainder:
            raise SplitAbortedError(
                f"Image dimension {length} is not evenly divisible by {count} (remainder {remainder})."
            )
        if mode == MODE_BLEED_PADDING:
            return [base + (1 if remainder else 0)] * count, remainder
        if mode == MODE_CROP_TO_FIT:
            # Crop to fit: all tiles are base size, remainder is discarded
            return [base] * count, remainder
        # Put the one-pixel increases on right/bottom tiles, preserving source bounds.
        return [base] * (count - remainder) + [base + 1] * remainder, remainder

    @staticmethod
    def _edge_pad(image: Image.Image, width: int, height: int) -> Image.Image:
        """Pad right/bottom with repeated edge pixels without an array-sized copy."""
        if image.size == (width, height):
            return image
        padded = Image.new(image.mode, (width, height))
        source_width, source_height = image.size
        padded.paste(image, (0, 0))
        if width > source_width:
            edge = image.crop((source_width - 1, 0, source_width, source_height))
            padded.paste(edge.resize((width - source_width, source_height)), (source_width, 0))
        if height > source_height:
            edge = padded.crop((0, source_height - 1, width, source_height))
            padded.paste(edge.resize((width, height - source_height)), (0, source_height))
        return padded

    @staticmethod
    def _texture_bleed_pad(image: Image.Image, width: int, height: int, bleed_radius: int = 0) -> Image.Image:
        """Pad using texture bleeding - extend edge pixels outward seamlessly.
        
        This method implements UV texture bleeding similar to 3D baking workflows.
        The outermost edge pixels are extruded outward into the padding zone,
        creating a seamless transition when tiles are tiled together.
        
        Algorithm:
        1. Extract edge columns/rows from the source image
        2. Extend these edge pixels outward by the required padding amount
        3. For corners, use the corner pixel value to fill the corner region
        4. The bleed_radius parameter controls how far edge pixels are extruded
           (useful for mipmapping and filtering artifacts)
        
        Args:
            image: Source image to pad
            width: Target width (must be >= image.width)
            height: Target height (must be >= image.height)
            bleed_radius: Number of pixels to extend edge values (0 = extend to full padding)
        
        Returns:
            Padded image with seamless edge extension
        """
        if image.size == (width, height):
            return image
        
        source_width, source_height = image.size
        pad_width = width - source_width
        pad_height = height - source_height
        
        if pad_width < 0 or pad_height < 0:
            raise ValueError("Target dimensions must be larger than source dimensions for padding.")
        
        # Create padded canvas
        padded = Image.new(image.mode, (width, height))
        padded.paste(image, (0, 0))
        
        # If no padding needed, return early
        if pad_width == 0 and pad_height == 0:
            return padded
        
        # Determine actual bleed distance (capped at padding size)
        bleed_dist = min(bleed_radius, max(pad_width, pad_height)) if bleed_radius > 0 else 0
        
        # Extract edge columns for horizontal padding
        if pad_width > 0:
            # Left edge column
            left_edge = image.crop((0, 0, 1, source_height))
            # Right edge column
            right_edge = image.crop((source_width - 1, 0, source_width, source_height))
            
            # Extend left edge to the left
            if bleed_dist > 0 and bleed_dist < pad_width:
                # Bleed zone: extend edge pixels by bleed_radius
                left_bleed = left_edge.resize((bleed_dist, source_height))
                padded.paste(left_bleed, (pad_width - bleed_dist, 0))
                # Fill remaining with last bleed pixel
                remaining = pad_width - bleed_dist
                if remaining > 0:
                    last_pixel = left_edge.resize((remaining, source_height))
                    padded.paste(last_pixel, (0, 0))
            else:
                # Extend full padding with edge pixel
                left_extended = left_edge.resize((pad_width, source_height))
                padded.paste(left_extended, (0, 0))
            
            # Extend right edge to the right
            if bleed_dist > 0 and bleed_dist < pad_width:
                right_bleed = right_edge.resize((bleed_dist, source_height))
                padded.paste(right_bleed, (source_width, 0))
                remaining = pad_width - bleed_dist
                if remaining > 0:
                    last_pixel = right_edge.resize((remaining, source_height))
                    padded.paste(last_pixel, (source_width + bleed_dist, 0))
            else:
                right_extended = right_edge.resize((pad_width, source_height))
                padded.paste(right_extended, (source_width, 0))
        
        # Extract edge rows for vertical padding
        if pad_height > 0:
            # Top edge row
            top_edge = padded.crop((0, 0, width, 1))
            # Bottom edge row (use padded to include horizontal extensions)
            bottom_edge = padded.crop((0, source_height - 1, width, source_height))
            
            # Extend top edge upward
            if bleed_dist > 0 and bleed_dist < pad_height:
                top_bleed = top_edge.resize((width, bleed_dist))
                padded.paste(top_bleed, (0, pad_height - bleed_dist))
                remaining = pad_height - bleed_dist
                if remaining > 0:
                    last_pixel = top_edge.resize((width, remaining))
                    padded.paste(last_pixel, (0, 0))
            else:
                top_extended = top_edge.resize((width, pad_height))
                padded.paste(top_extended, (0, 0))
            
            # Extend bottom edge downward
            if bleed_dist > 0 and bleed_dist < pad_height:
                bottom_bleed = bottom_edge.resize((width, bleed_dist))
                padded.paste(bottom_bleed, (0, source_height))
                remaining = pad_height - bleed_dist
                if remaining > 0:
                    last_pixel = bottom_edge.resize((width, remaining))
                    padded.paste(last_pixel, (0, source_height + bleed_dist))
            else:
                bottom_extended = bottom_edge.resize((width, pad_height))
                padded.paste(bottom_extended, (0, source_height))
        
        return padded

    @staticmethod
    def _reflect_pad(image: Image.Image, width: int, height: int) -> Image.Image:
        """Reflect-pad an image. NumPy is used only for this opt-in operation."""
        try:
            import numpy as np
        except ImportError as error:
            raise RuntimeError("Reflect padding requires NumPy. Install it with 'pip install numpy'.") from error
        if image.size == (width, height):
            return image
        array = np.asarray(image)
        pad_height = height - image.height
        pad_width = width - image.width
        if array.ndim == 2:
            padding = ((0, pad_height), (0, pad_width))
        else:
            padding = ((0, pad_height), (0, pad_width), (0, 0))
        return Image.fromarray(np.pad(array, padding, mode="reflect"))

    @classmethod
    def _pad(cls, image: Image.Image, width: int, height: int, padding_mode: PaddingMode, 
            bleed_radius: int = 0) -> Image.Image:
        if padding_mode == "edge":
            return cls._edge_pad(image, width, height)
        if padding_mode == "reflect":
            return cls._reflect_pad(image, width, height)
        if padding_mode == "texture_bleed":
            return cls._texture_bleed_pad(image, width, height, bleed_radius)
        raise ValueError(f"Unsupported padding mode: {padding_mode!r}")

    @staticmethod
    def _is_blank_tile(image: Image.Image) -> bool:
        """Check if a tile is completely blank (fully transparent).
        
        Returns True if all pixels have alpha = 0 (fully transparent).
        For images without alpha channel, returns False.
        """
        if image.mode not in {"RGBA", "LA", "PA"}:
            # No alpha channel, cannot be blank
            return False
        
        # Get alpha channel
        alpha = image.getchannel("A")
        
        # Check if all alpha values are 0
        try:
            import numpy as np
            alpha_array = np.array(alpha)
            return np.all(alpha_array == 0)
        except ImportError:
            # Fallback without numpy - check pixel by pixel
            # This is slower but works without numpy
            alpha_data = alpha.getdata()
            return all(pixel == 0 for pixel in alpha_data)

    @staticmethod
    def _save(image: Image.Image, path: Path, settings: ExportSettings,
              icc_profile: Optional[bytes]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = settings.image_format.upper().replace("JPG", "JPEG")
        save_image = image
        options: dict[str, object] = {}
        if icc_profile:
            options["icc_profile"] = icc_profile
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
            if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA"}:
                save_image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            options.update(compress_level=settings.png_compress_level, optimize=settings.png_optimize)
        elif fmt == "WEBP":
            options.update(quality=settings.quality, lossless=settings.webp_lossless)
        save_image.save(path, format=fmt, **options)

    @staticmethod
    def _name(template: str, basename: str, row: int, column: int, index: int, extension: str,
              tile_width: int = 0, tile_height: int = 0) -> str:
        try:
            name = template.format(basename=basename, row=row, col=column, column=column,
                                   index=index, ext=extension, width=tile_width, height=tile_height)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Invalid naming template: {template!r}") from error
        if not name:
            raise ValueError("The naming template produced an empty filename.")
        return name

    def split_grid(self, source: str | Path, output_directory: str | Path, rows: int, columns: int,
                   resolution_mode: ResolutionMode = MODE_ALLOW_VARIATION,
                   padding_mode: PaddingMode = "edge",
                   export: ExportSettings = ExportSettings(),
                   naming_template: str = "{basename}_r{row}_c{col}_w{width}_h{height}.{ext}") -> SplitResult:
        """Split ``source`` into a grid and export all tiles.

        ``allow_variation`` keeps the original canvas and assigns remainder pixels to
        the right/bottom tiles. ``bleed_padding`` edge- or reflect-pads the canvas to
        equal tile dimensions. ``crop_to_fit`` discards remainder pixels. ``abort`` raises
        :class:`SplitAbortedError` on a remainder before any output is written.
        """
        # Validate file count before processing
        estimated_count = rows * columns
        should_proceed, warning_msg = self._validate_file_count(estimated_count)
        if not should_proceed:
            raise ValueError(warning_msg)
        if warning_msg:
            self._emit(SplitStatus("warning", warning_msg))
            self._confirm_warning(warning_msg)
        
        with self._lock:
            # Load image with context manager
            with Image.open(source) as opened:
                opened.load()
                image = opened.copy()
                icc_profile = opened.info.get("icc_profile")

            # Get original image size
            original_size = image.size

            # Get tile dimensions
            widths, width_remainder = self._axis_sizes(image.width, columns, resolution_mode)
            heights, height_remainder = self._axis_sizes(image.height, rows, resolution_mode)

            # Handle remainder
            if width_remainder or height_remainder:
                self._emit(SplitStatus(
                    "remainder", "Grid does not divide evenly; tile dimensions are being resolved.",
                    image_size=original_size, grid_size=(rows, columns),
                    remainder=(width_remainder, height_remainder),
                ))

            # Pad image (only for bleed_padding mode)
            if resolution_mode == MODE_BLEED_PADDING:
                image = self._pad(image, sum(widths), sum(heights), padding_mode, export.bleed_radius)

            # Get tile edges
            x_edges = [0]
            y_edges = [0]

            for width in widths:
                x_edges.append(x_edges[-1] + width)
            for height in heights:
                y_edges.append(y_edges[-1] + height)

        destination = Path(output_directory)
        basename = Path(source).stem
        tiles: list[Tile] = []
        total = rows * columns
        skipped_count = 0
        futures: list[_cf.Future] = []
        next_index = 0

        def make_save_task(tile_img, path, idx, row_i, col_i, box_coords, tile_size):
            def task():
                if self._check_abort():
                    return

                try:
                    self._save(tile_img, path, export, icc_profile)
                except Exception:
                    raise
                else:
                    tile = Tile(idx, row_i, col_i, box_coords, path, tile_size)

                    with self._lock:
                        tiles.append(tile)
                        completed = len(tiles)

                    self._emit(
                        SplitStatus(
                            "tile_saved",
                            f"Saved {path.name}",
                            completed,
                            total,
                            image.size,
                            (rows, columns),
                            (width_remainder, height_remainder),
                        )
                    )
            return task

        for row in range(rows):
            for column in range(columns):
                # Check for abort before processing each tile.
                if self._check_abort():
                    image.close()
                    self._emit_aborted()

                    # Cancel queued futures that have not started yet.
                    for future in futures:
                        future.cancel()

                    return SplitResult(
                        tuple(tiles),
                        (sum(widths), sum(heights)),
                        original_size
                    )
                box = (x_edges[column], y_edges[row], x_edges[column + 1], y_edges[row + 1])
                tile_width = x_edges[column + 1] - x_edges[column]
                tile_height = y_edges[row + 1] - y_edges[row]

                with image.crop(box) as tile_image:
                    # Check if tile is blank and should be discarded
                    if export.discard_blank_tiles and self._is_blank_tile(tile_image):
                        skipped_count += 1
                        self._emit(SplitStatus("tile_skipped", f"Skipped blank tile at row {row}, column {column}", 
                                               len(tiles) + skipped_count, total,
                                               image.size, (rows, columns),
                                               (width_remainder, height_remainder)))
                        continue

                    # Prepare tile copy for safe async saving
                    tile_copy = tile_image.copy()
                    index = next_index
                    next_index += 1
                    filename = self._name(naming_template, basename, row, column, index, export.extension,
                                          tile_width, tile_height)
                    path = destination / filename

                    # Create save task
                    task = make_save_task(tile_copy, path, index, row, column, box, (tile_width, tile_height))
                    if self._save_executor is not None:
                        futures.append(self._save_executor.submit(task))
                    else:
                        # Execute synchronously in current thread
                        task()

        image.close()

        if futures:
            for f in _cf.as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

        if skipped_count > 0:
            self._emit(SplitStatus("complete", f"Skipped {skipped_count} blank tile(s). Exported {len(tiles)} tile(s).",
                                   len(tiles), total, image.size, (rows, columns),
                                   (width_remainder, height_remainder)))

        return SplitResult(tuple(tiles), (sum(widths), sum(heights)), original_size)

    def split_dimensions(self, source: str | Path, output_directory: str | Path,
                         tile_width: int, tile_height: int,
                         resolution_mode: ResolutionMode = MODE_ALLOW_VARIATION,
                         padding_mode: PaddingMode = "edge",
                         export: ExportSettings = ExportSettings(),
                         naming_template: str = "{basename}_r{row}_c{col}_w{width}_h{height}.{ext}") -> SplitResult:
        """Split using fixed tile pixel dimensions.

        In variation mode the final row/column may be smaller. Padding mode creates
        full-size edge/reflection-padded boundary tiles. Crop_to_fit discards partial tiles.
        Abort rejects partial tiles.
        """
        if tile_width <= 0 or tile_height <= 0:
            raise ValueError("tile_width and tile_height must be positive.")
        
        # Validate file count before processing
        # Need the source image size to estimate total files without loading full image yet
        with Image.open(source) as _probe:
            img_w, img_h = _probe.size
        estimated_count = ((img_w + tile_width - 1) // tile_width) * ((img_h + tile_height - 1) // tile_height)
        should_proceed, warning_msg = self._validate_file_count(estimated_count)
        if not should_proceed:
            raise ValueError(warning_msg)
        if warning_msg:
            self._emit(SplitStatus("warning", warning_msg))
            self._confirm_warning(warning_msg)
        with self._lock:
            # Load image with context manager
            with Image.open(source) as opened:
                opened.load()
                image = opened.copy()
                icc_profile = opened.info.get("icc_profile")
            
            original_size = image.size
            columns = (image.width + tile_width - 1) // tile_width
            rows = (image.height + tile_height - 1) // tile_height
            remainder = (image.width % tile_width, image.height % tile_height)
            
            if resolution_mode == MODE_ABORT and any(remainder):
                image.close()
                raise SplitAbortedError("Image dimensions do not divide evenly into the requested tile size.")
            
            if resolution_mode == MODE_CROP_TO_FIT and any(remainder):
                # Adjust grid to exclude partial tiles
                columns = image.width // tile_width
                rows = image.height // tile_height
                remainder = (0, 0)
                self._emit(SplitStatus("crop", "Cropping to fit: partial tiles discarded.",
                                       image_size=original_size, grid_size=(rows, columns), remainder=remainder))
            
            if any(remainder):
                self._emit(SplitStatus("remainder", "Boundary tiles require resolution.",
                                       image_size=original_size, grid_size=(rows, columns), remainder=remainder))
            
            if resolution_mode == MODE_BLEED_PADDING:
                image = self._pad(image, columns * tile_width, rows * tile_height, padding_mode, export.bleed_radius)

        destination = Path(output_directory)
        basename = Path(source).stem
        tiles: list[Tile] = []
        total = rows * columns
        skipped_count = 0
        futures: list[_cf.Future] = []
        next_index = 0

        def make_save_task(tile_img, path, idx, row_i, col_i, box_coords, tile_size):
            def task():
                try:
                    self._save(tile_img, path, export, icc_profile)
                finally:
                    tile = Tile(idx, row_i, col_i, box_coords, path, tile_size)
                    with self._lock:
                        tiles.append(tile)
                        completed = len(tiles)
                    self._emit(SplitStatus("tile_saved", f"Saved {path.name}", completed, total,
                                           image.size, (rows, columns), remainder))
            return task

        for row in range(rows):
            for column in range(columns):
                # Check for abort before processing each tile.
                self._wait_if_paused()
                if self._check_abort():
                    image.close()
                    self._emit_aborted()

                    # Cancel queued futures that have not started yet.
                    for future in futures:
                        future.cancel()

                    return SplitResult(
                        tuple(tiles),
                        image.size,
                        original_size
                    )
                right = min((column + 1) * tile_width, image.width)
                bottom = min((row + 1) * tile_height, image.height)
                actual_tile_width = right - (column * tile_width)
                actual_tile_height = bottom - (row * tile_height)
                box = (column * tile_width, row * tile_height, right, bottom)

                with image.crop(box) as tile_image:
                    # Check if tile is blank and should be discarded
                    if export.discard_blank_tiles and self._is_blank_tile(tile_image):
                        skipped_count += 1
                        self._emit(SplitStatus("tile_skipped", f"Skipped blank tile at row {row}, column {column}",
                                               len(tiles) + skipped_count, total,
                                               image.size, (rows, columns), remainder))
                        continue

                    tile_copy = tile_image.copy()
                    index = next_index
                    next_index += 1
                    path = destination / self._name(naming_template, basename, row, column, index, export.extension,
                                                   actual_tile_width, actual_tile_height)

                    task = make_save_task(tile_copy, path, index, row, column, box, (actual_tile_width, actual_tile_height))
                    if self._save_executor is not None:
                        futures.append(self._save_executor.submit(task))
                    else:
                        task()

        image.close()

        if futures:
            for f in _cf.as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

        if skipped_count > 0:
            self._emit(SplitStatus("complete", f"Skipped {skipped_count} blank tile(s). Exported {len(tiles)} tile(s).",
                                   len(tiles), total, image.size, (rows, columns), remainder))

        return SplitResult(tuple(tiles), image.size, original_size)

    @staticmethod
    def _alpha_components(image: Image.Image, alpha_threshold: int) -> Sequence[tuple[int, int, int, int]]:
        """Return 8-connected non-transparent bounding boxes using NumPy flood fill."""
        if "A" not in image.getbands():
            raise ValueError("Transparency auto-detect requires an image with an alpha channel.")
        if not 0 <= alpha_threshold <= 255:
            raise ValueError("alpha_threshold must be in the range 0..255.")
        try:
            import numpy as np
        except ImportError as error:
            raise RuntimeError("Transparency auto-detect requires NumPy. Install it with 'pip install numpy'.") from error
        mask = np.asarray(image.getchannel("A")) > alpha_threshold
        try:
            import cv2
        except ImportError:
            cv2 = None
        if cv2 is not None:
            component_count, _, statistics, _ = cv2.connectedComponentsWithStats(
                mask.astype(np.uint8), connectivity=8
            )
            return [
                (int(left), int(top), int(left + width), int(top + height))
                for left, top, width, height, _ in statistics[1:component_count]
            ]
        visited = np.zeros(mask.shape, dtype=bool)
        height, width = mask.shape
        boxes: list[tuple[int, int, int, int]] = []
        for start_y, start_x in np.argwhere(mask):
            if visited[start_y, start_x]:
                continue
            stack = [(int(start_y), int(start_x))]
            visited[start_y, start_x] = True
            left = right = int(start_x)
            top = bottom = int(start_y)
            while stack:
                y, x = stack.pop()
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
                for next_y in range(max(0, y - 1), min(height, y + 2)):
                    for next_x in range(max(0, x - 1), min(width, x + 2)):
                        if mask[next_y, next_x] and not visited[next_y, next_x]:
                            visited[next_y, next_x] = True
                            stack.append((next_y, next_x))
            boxes.append((left, top, right + 1, bottom + 1))
        return sorted(boxes, key=lambda box: (box[1], box[0]))

    def split_transparent_components(self, source: str | Path, output_directory: str | Path,
                                     alpha_threshold: int = 0,
                                     export: ExportSettings = ExportSettings(),
                                     naming_template: str = "{basename}_tile_{index}_w{width}_h{height}.{ext}") -> SplitResult:
        """Export one crop per 8-connected non-transparent alpha component."""
        with self._lock:
            # Load image with context manager
            with Image.open(source) as opened:
                opened.load()
                image = opened.copy()
                icc_profile = opened.info.get("icc_profile")
            
            boxes = self._alpha_components(image, alpha_threshold)
        
        destination = Path(output_directory)
        basename = Path(source).stem
        tiles: list[Tile] = []
        futures: list[_cf.Future] = []

        total = len(boxes)

        def make_save_task(tile_img, path, idx, box_coords, tile_size):
            def task():
                try:
                    self._save(tile_img, path, export, icc_profile)
                finally:
                    tile = Tile(idx, 0, 0, box_coords, path, tile_size)
                    with self._lock:
                        tiles.append(tile)
                        completed = len(tiles)
                    self._emit(SplitStatus("tile_saved", f"Saved {path.name}", completed, total, image.size))
            return task

        for index, box in enumerate(boxes):
            # Check for abort before processing each component.
            self._wait_if_paused()
            if self._check_abort():
                image.close()
                self._emit_aborted()

                # Cancel queued futures that have not started yet.
                for future in futures:
                    future.cancel()

                return SplitResult(
                    tuple(tiles),
                    image.size,
                    image.size
                )
            
            tile_width = box[2] - box[0]
            tile_height = box[3] - box[1]
            path = destination / self._name(naming_template, basename, 0, 0, index, export.extension,
                                           tile_width, tile_height)
            
            with image.crop(box) as tile_image:
                tile_copy = tile_image.copy()
                task = make_save_task(tile_copy, path, index, box, (tile_width, tile_height))
                if self._save_executor is not None:
                    futures.append(self._save_executor.submit(task))
                else:
                    task()

        image.close()

        if futures:
            for f in _cf.as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

        return SplitResult(tuple(tiles), image.size, image.size)

    def split_custom_grid(self, source: str | Path, output_directory: str | Path,
                          row_heights: Sequence[int], column_widths: Sequence[int],
                          resolution_mode: ResolutionMode = MODE_ALLOW_VARIATION,
                          padding_mode: PaddingMode = "edge",
                          export: ExportSettings = ExportSettings(),
                          naming_template: str = "{basename}_r{row}_c{col}_w{width}_h{height}.{ext}") -> SplitResult:
        """Split using custom row heights and column widths for maximum flexibility.

        This method allows non-uniform grid dimensions where each row can have a different
        height and each column can have a different width. This is useful for creating
        grids with varying tile sizes based on content requirements.

        Args:
            source: Path to the source image.
            output_directory: Directory where tiles will be saved.
            row_heights: Sequence of heights for each row (in pixels).
            column_widths: Sequence of widths for each column (in pixels).
            resolution_mode: How to handle remainder pixels at edges.
            padding_mode: Padding mode when using bleed_padding.
            export: Export settings for output tiles.
            naming_template: Filename template with placeholders.

        Returns:
            SplitResult containing tile metadata and canvas information.
        """
        if not row_heights or not column_widths:
            raise ValueError("row_heights and column_widths must be non-empty sequences.")
        
        # Validate file count before processing
        estimated_count = len(row_heights) * len(column_widths)
        should_proceed, warning_msg = self._validate_file_count(estimated_count)
        if not should_proceed:
            raise ValueError(warning_msg)
        if warning_msg:
            self._emit(SplitStatus("warning", warning_msg))
            self._confirm_warning(warning_msg)
        if any(h <= 0 for h in row_heights):
            raise ValueError("All row heights must be positive.")
        if any(w <= 0 for w in column_widths):
            raise ValueError("All column widths must be positive.")
        
        with self._lock:
            # Load image with context manager
            with Image.open(source) as opened:
                opened.load()
                image = opened.copy()
                icc_profile = opened.info.get("icc_profile")
            
            original_size = image.size
            rows = len(row_heights)
            columns = len(column_widths)
            
            total_width = sum(column_widths)
            total_height = sum(row_heights)
            
            width_remainder = image.width - total_width
            height_remainder = image.height - total_height
            
            if resolution_mode == MODE_ABORT and (width_remainder < 0 or height_remainder < 0):
                image.close()
                raise SplitAbortedError(
                    f"Custom grid dimensions ({total_width}x{total_height}) exceed image size ({image.width}x{image.height})."
                )
            
            if width_remainder < 0 or height_remainder < 0:
                self._emit(SplitStatus(
                    "remainder", "Custom grid exceeds image dimensions; tiles will be cropped.",
                    image_size=original_size, grid_size=(rows, columns),
                    remainder=(width_remainder, height_remainder),
                ))
            
            # Handle padding mode
            if resolution_mode == MODE_BLEED_PADDING:
                if width_remainder > 0 or height_remainder > 0:
                    # Extend the last row/column to fill the image with texture bleeding
                    column_widths = list(column_widths)
                    row_heights = list(row_heights)
                    column_widths[-1] += width_remainder
                    row_heights[-1] += height_remainder
                    total_width = sum(column_widths)
                    total_height = sum(row_heights)
                    width_remainder = 0
                    height_remainder = 0
                    self._emit(SplitStatus("padding", "Extended last row/column to fill image with texture bleeding.",
                                           image_size=original_size, grid_size=(rows, columns),
                                           remainder=(0, 0)))
                    # Apply texture bleeding to the image
                    image = self._pad(image, total_width, total_height, padding_mode, export.bleed_radius)
            
            # Calculate edge positions
            x_edges = [0]
            for width in column_widths:
                x_edges.append(x_edges[-1] + width)
            
            y_edges = [0]
            for height in row_heights:
                y_edges.append(y_edges[-1] + height)
        
        destination = Path(output_directory)
        basename = Path(source).stem
        tiles: list[Tile] = []
        total = rows * columns
        skipped_count = 0
        futures: list[_cf.Future] = []
        next_index = 0

        def make_save_task(tile_img, path, idx, row_i, col_i, box_coords, tile_size):
            def task():
                try:
                    self._save(tile_img, path, export, icc_profile)
                finally:
                    tile = Tile(idx, row_i, col_i, box_coords, path, tile_size)
                    with self._lock:
                        tiles.append(tile)
                        completed = len(tiles)
                    self._emit(SplitStatus("tile_saved", f"Saved {path.name}", completed, total,
                                           image.size, (rows, columns),
                                           (width_remainder, height_remainder)))
            return task

        for row in range(rows):
            for column in range(columns):
                # Check for abort before processing each tile.
                self._wait_if_paused()
                if self._check_abort():
                    image.close()
                    self._emit_aborted()

                    # Cancel queued futures that have not started yet.
                    for future in futures:
                        future.cancel()

                    return SplitResult(
                        tuple(tiles),
                        (total_width, total_height),
                        original_size
                    )

                box = (x_edges[column], y_edges[row], x_edges[column + 1], y_edges[row + 1])
                tile_width = x_edges[column + 1] - x_edges[column]
                tile_height = y_edges[row + 1] - y_edges[row]
                
                # Ensure box is within image bounds
                box = (box[0], box[1], min(box[2], image.width), min(box[3], image.height))
                actual_tile_width = box[2] - box[0]
                actual_tile_height = box[3] - box[1]
                
                if actual_tile_width <= 0 or actual_tile_height <= 0:
                    skipped_count += 1
                    self._emit(SplitStatus("tile_skipped", f"Skipped empty tile at row {row}, column {column}",
                                           len(tiles) + skipped_count, total,
                                           image.size, (rows, columns),
                                           (width_remainder, height_remainder)))
                    continue
                
                with image.crop(box) as tile_image:
                    # Check if tile is blank and should be discarded
                    if export.discard_blank_tiles and self._is_blank_tile(tile_image):
                        skipped_count += 1
                        self._emit(SplitStatus("tile_skipped", f"Skipped blank tile at row {row}, column {column}",
                                               len(tiles) + skipped_count, total,
                                               image.size, (rows, columns),
                                               (width_remainder, height_remainder)))
                        continue
                    
                    tile_copy = tile_image.copy()
                    index = next_index
                    next_index += 1
                    filename = self._name(naming_template, basename, row, column, index, export.extension,
                                         actual_tile_width, actual_tile_height)
                    path = destination / filename
                    task = make_save_task(tile_copy, path, index, row, column, box, (actual_tile_width, actual_tile_height))
                    if self._save_executor is not None:
                        futures.append(self._save_executor.submit(task))
                    else:
                        task()

        image.close()

        if futures:
            for f in _cf.as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

        if skipped_count > 0:
            self._emit(SplitStatus("complete", f"Skipped {skipped_count} tile(s). Exported {len(tiles)} tile(s).",
                                   len(tiles), total, image.size, (rows, columns),
                                   (width_remainder, height_remainder)))
        
        return SplitResult(tuple(tiles), (total_width, total_height), original_size)