"""Convert image-frame sequences to video and animated image formats with FFmpeg."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Sequence
from PIL import Image, UnidentifiedImageError


class ImageToVideo:
    """Build and run FFmpeg commands for a directory of equally typed image frames."""

    OUTPUT_TYPES = frozenset({"mp4_h264", "mp4_av1", "webm", "gif", "apng", "webp"})

    def __init__(self, folder: str, output: str, output_type: str = "mp4_h264",
                 transparent_webm: bool = False, fps: float = 30,
                 crf: Optional[int] = 18, amount_threads: int = 1,
                 background_color: tuple[int, int, int] = (0, 0, 0),
                 quality_mode: str = "crf", bitrate: Optional[int] = None) -> None:
        self.path_in = Path(folder)
        self.path_out = Path(output)
        self.output_type = output_type
        self.transparent_webm = transparent_webm
        self.fps = fps
        self.crf = crf
        self.amount_threads = amount_threads
        self.background_color = background_color
        self.quality_mode = quality_mode
        self.bitrate = bitrate
        self.ffmpeg = ImageToVideo._resolve_ffmpeg()
        self.list_txt: Optional[str] = None

        self.width, self.height = self._get_dimensions_from_first_frame()

    def _get_dimensions_from_first_frame(self) -> tuple[int, int]:
        try:
            with Image.open(self._frame_paths()[0]) as img:
                return img.size
        except (IOError, IndexError) as e:
            raise ValueError("First frame is not a valid image.") from e

    @staticmethod
    def get_dimensions_from_first_frame_static(dir_path: str) -> tuple[int, int]:
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    with Image.open(entry.path) as img:
                        return img.size

            raise FileNotFoundError("No frames found in folder.")
        except IndexError as e:
            raise FileNotFoundError("No frames found or invalid frame indexes in folder.") from e
        except (IOError, OSError) as e:
            raise OSError("First frame is corrupted, not found, or cannot be read.") from e

    def is_path_exist(self) -> bool:
        """Return whether the configured input directory exists."""
        return self.path_in.is_dir()

    def _frame_paths(self) -> list[Path]:
        """Return source frames in a reproducible order, excluding the output itself."""
        output_path = self.path_out.resolve(strict=False)
        return sorted(
            (path for path in self.path_in.iterdir()
             if path.is_file() and not path.name.startswith(".")
             and path.resolve(strict=False) != output_path),
            key=lambda path: path.name.casefold(),
        )

    def get_extension(self) -> str:
        """Return the extension of the first non-hidden input frame."""
        frames = self._frame_paths()
        if not frames:
            raise FileNotFoundError("No frames found in folder.")
        return frames[0].suffix

    @staticmethod
    def _concat_path(path: Path) -> str:
        """Escape one path for an FFmpeg concat-demuxer list."""
        return "file '" + path.resolve().as_posix().replace("'", r"\'") + "'\n"

    def generate_temp_file_list(self) -> str | None:
        """Create a unique FFmpeg concat list and return its path."""
        self.cleanup()
        frames = list(self._frame_paths())
        if not frames:
            return None

        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".ffconcat",
                                             prefix="frames-to-video-", delete=False)
        success = False

        try:
            handle.write("ffconcat version 1.0\n")

            frame_duration = 1.0 / self.fps

            for frame in frames:
                path = frame.resolve().as_posix().replace("'",r"'\''")

                handle.write(f"file '{path}'\n")
                handle.write(f"duration {frame_duration:.9f}\n")

            last_path = frames[-1].resolve().as_posix().replace("'", r"'\''")
            handle.write(f"file '{last_path}'\n")

            success = True
        finally:
            handle.close()
            if not success and os.path.exists(handle.name):
                try:
                    os.unlink(handle.name)
                except OSError:
                    pass

        self.list_txt = handle.name
        return self.list_txt

    def cleanup(self) -> None:
        """Remove this conversion's temporary concat list, if it still exists."""
        if self.list_txt:
            try:
                Path(self.list_txt).unlink(missing_ok=True)
            finally:
                self.list_txt = None

    def _input_command(self) -> list[str]:
        if not self.list_txt:
            raise RuntimeError("Generate the frame list before building an FFmpeg command.")
        return [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-r", str(self.fps),
                "-f", "concat", "-safe", "0", "-i", self.list_txt]

    def _padded_filter(self, transparent: bool = False) -> str:
        w, h = self.width, self.height

        # make it even dimensional to prevent codec errors
        target_w = (w // 2) * 2
        target_h = (h // 2) * 2

        scale_part_field = f"scale={target_w}:{target_h}"
        force_aspect_ratio_part_field = "force_original_aspect_ratio=decrease"
        pad_part_field = f"pad={target_w}:{target_h}"
        padding = "(ow-iw)/2:(oh-ih)/2"

        if transparent:
            return f"{scale_part_field}:{force_aspect_ratio_part_field},{pad_part_field}:{padding}:color=0x000000@0"
        else:
            # Add background color compositing for non-transparent formats
            r, g, b = self.background_color
            bg_hex = f"0x{r:02x}{g:02x}{b:02x}"

            # Composite over background color: overlay the video on a solid color background
            return (
                f"color=c={bg_hex}:s={target_w}x{target_h}[bg];"
                f"[0:v]{scale_part_field}:{force_aspect_ratio_part_field}[vid];"
                f"[bg][vid]overlay=(W-w)/2:(H-h)/2:shortest=1"
            )

    def pre_generate_cmd_mp4(self, additional_arguments: Sequence[str] = (), pass_num: int | None = None) -> list[str]:
        """Build an H.264 or AV1-in-MP4 FFmpeg command."""
        command = self._input_command() + ["-vf", self._padded_filter(), "-pix_fmt", "yuv420p",
                                            "-threads", str(self.amount_threads)]

        if self.bitrate is not None and int(self.bitrate) == 0:
            raise ValueError("Bitrate cannot be 0.")

        if self.output_type == "mp4_av1":
            command += ["-c:v", "libsvtav1", "-preset", "6"]
            if self.quality_mode == "crf":
                command += ["-crf", str(self.crf or 30), "-b:v", "0"]
            elif self.bitrate:
                command += ["-b:v", f"{self.bitrate}k"]

        else:
            command += ["-c:v", "libx264", "-preset", "medium"]
            if self.quality_mode == "crf":
                command += ["-crf", str(self.crf or 18)]
            elif self.bitrate:
                command += ["-b:v", f"{self.bitrate}k"]

        if self.quality_mode == "2-pass vbr":
            if pass_num == 1:
                command += ["-pass", "1", *additional_arguments, "-f", "null", "-"]
            elif pass_num == 2:
                command += ["-pass", "2", *additional_arguments, "-movflags", "+faststart", str(self.path_out)]
            else:
                raise ValueError(f"Invalid pass number for 2-pass VBR mode (Accepted: {pass_num})")
        else:
            command += [*additional_arguments, "-movflags", "+faststart", str(self.path_out)]

        return command

    def pre_generate_cmd_webm(self, additional_arguments: Sequence[str] = (),
                              transparent: bool = False, pass_num: int | None = None) -> list[str]:
        """Build a VP9 WebM command, optionally preserving alpha."""
        command = self._input_command() + [
            "-vf", self._padded_filter(transparent), "-c:v", "libvpx-vp9", "-pix_fmt",
            "yuva420p" if transparent else "yuv420p", "-an", "-threads",
            str(self.amount_threads), "-row-mt", "1",
        ]
        
        if self.quality_mode == "crf":
            command += ["-crf", str(self.crf or 18), "-b:v", "0"]
        elif self.bitrate:
            command += ["-b:v", f"{self.bitrate}k"]
        
        if transparent:
            command += ["-auto-alt-ref", "0"]

        if self.quality_mode == "2-pass vbr":
            if pass_num == 1:
                command += ["-pass", "1", *additional_arguments, "-f", "null", "-"]
            elif pass_num == 2:
                command += ["-pass", "2", *additional_arguments, str(self.path_out)]
            else:
                raise ValueError(f"Invalid pass number for 2-pass VBR mode (Accepted: {pass_num})")

        else:
            command += [*additional_arguments, str(self.path_out)]

        return command

    def pre_generate_cmd_apng(self, additional_arguments: Sequence[str] = (),
                              transparent: bool = False) -> list[str]:
        """Build an APNG command, optionally preserving alpha."""
        return self._input_command() + [
            "-vf", self._padded_filter(transparent), "-c:v", "apng", "-pix_fmt",
            "rgba" if transparent else "rgb24", "-plays", "0", "-threads",
            str(self.amount_threads), *additional_arguments, "-f", "apng", str(self.path_out),
        ]

    def pre_generate_cmd_webp(self, additional_arguments: Sequence[str] = (),
                              transparent: bool = False) -> list[str]:
        pix_fmt = "rgba" if transparent else "yuv420p"

        command = self._input_command() + [
            "-vf", self._padded_filter(transparent),
            "-c:v", "libwebp", "-pix_fmt", pix_fmt,
            "-loop", "0",
            "-threads", str(self.amount_threads)
        ]

        if hasattr(self, "quality_mode") and self.quality_mode == "crf":
            command += ["-crf", str(self.crf or 18)]
        elif hasattr(self, "quality_mode") and self.quality_mode == "lossless":
            command += ["-lossless", "1"]
        elif getattr(self, "bitrate", None):
            command += ["-b:v", f"{self.bitrate}k"]

        command += [*additional_arguments, str(self.path_out)]

        return command

    def pre_generate_cmd_gif(self, additional_arguments: Sequence[str] = (),
                            transparent: bool = False, gif_max_colors: Optional[int] = None) -> tuple[list[str], list[str], Path]:
        """Build GIF palette generation and encoding commands.
        
        Returns:
            tuple: (palette_command, gif_command, palette_path)
        """
        max_colors = max(4, min(int(gif_max_colors) if gif_max_colors else 256, 256))
        palette_path = self._temporary_output_path(".png")
        
        # Generate palette from frames (filter chain includes shortest=1 to prevent infinite loops)
        palette_filter = f"{self._padded_filter(transparent=transparent)},palettegen=max_colors={max_colors}"
        palette_command = self._input_command() + [
            "-vf", palette_filter,
            str(palette_path)
        ]
        
        # Use the generated palette when encoding (filter chain includes shortest=1 to prevent infinite loops)
        gif_filter = f"{self._padded_filter(transparent=transparent)},paletteuse"
        gif_command = self._input_command() + [
            "-i", str(palette_path),
            "-lavfi", gif_filter,
            "-threads", str(self.amount_threads),
            *additional_arguments,
            str(self.path_out)
        ]
        
        return palette_command, gif_command, palette_path

    @staticmethod
    def _temporary_output_path(suffix: str) -> Path:
        """Create a temporary output path for FFmpeg by safely"""
        descriptor, path = tempfile.mkstemp(suffix=suffix, prefix="frames-to-video-")
        try:
            os.close(descriptor)
        except OSError:
            pass
        p = Path(path)

        # If the physical file cannot exist before being used by FFmpeg:
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
        return p

    @staticmethod
    def _run_ffmpeg(command: Sequence[str], expected_total: int,
                    progress_callback: Optional[Callable[[int], None]] = None,
                    start_offset: int = 0, end_offset: int = 100, abort_event=None,
                    pause_event=None) -> None:
        """Run FFmpeg, report progress, and always release its process resources."""
        if "-f" in command and "null" in command:
            # For Pass 1
            f_index = command.index("-f")
            command_with_progress = [*command[:f_index], "-progress", "pipe:1", "-nostats", *command[f_index:]]
        else:
            # For Pass 2 and standard mode
            command_with_progress = [*command[:-1], "-progress", "pipe:1", "-nostats", command[-1]]

        process = subprocess.Popen(
            command_with_progress, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # check the command print
        diagnostics: list[str] = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                # Cooperative pause: FFmpeg naturally throttles when the progress
                # pipe is not drained, so blocking here suspends the encode.
                while pause_event is not None and pause_event.is_set():
                    if abort_event is not None and abort_event.is_set():
                        raise RuntimeError("ABORTED_BY_USER")
                    time.sleep(0.1)
                diagnostics.append(line)
                if len(diagnostics) > 50:
                    diagnostics.pop(0)
                if abort_event is not None and abort_event.is_set():
                    raise RuntimeError("ABORTED_BY_USER")
                if progress_callback and line.startswith("frame="):
                    try:
                        frame = int(line.partition("=")[2].strip())
                        fraction = min(1.0, max(0.0, frame / expected_total))
                        progress_callback(int(start_offset + (end_offset - start_offset) * fraction))
                    except (TypeError, ValueError):
                        pass
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()
        if process.returncode:
            raise subprocess.CalledProcessError(
                process.returncode,
                command_with_progress,
                output="".join(diagnostics),
            )

    def run(self) -> None:
        """Convert this instance's source using its selected output format."""
        self.frames_to_video(str(self.path_in), str(self.path_out), self.output_type,
                             self.transparent_webm, self.fps, self.crf,
                             amount_threads=self.amount_threads,
                             apng_transparent=self.transparent_webm)

    @staticmethod
    def frames_to_video(folder: str, output: str, output_type: str = "mp4_h264",
                        transparent_webm: bool = False, fps: float = 30,
                        crf: Optional[int] = 18,
                        progress_callback: Optional[Callable[[int], None]] = None,
                        amount_threads: int = 1, abort_event=None, pause_event=None,
                        gif_max_colors: Optional[int] = None,
                        apng_transparent: bool = False,
                        gif_transparent: bool = False,
                        webp_transparent: bool = False,
                        background_color: tuple[int, int, int] = (0, 0, 0),
                        quality_mode: str = "crf", bitrate: Optional[int] = None) -> None:
        """Convert one directory of frames to MP4, WebM, GIF, or APNG.

        This function detects whether the input frames contain an alpha channel and
        automatically composites them over the selected background color when the
        target format does not support transparency. WebM (when transparent_webm
        is True) and APNG may preserve alpha.
        """
        if not isinstance(output_type, str) or output_type not in ImageToVideo.OUTPUT_TYPES:
            # Compatibility with frames_to_video(folder, output, fps, crf, ...).
            fps, crf, output_type, transparent_webm = output_type, transparent_webm, "mp4_h264", False
        try:
            fps = float(fps)
        except (TypeError, ValueError) as error:
            raise ValueError("FPS must be a positive number.") from error
        if fps <= 0:
            raise ValueError("FPS must be a positive number.")
        try:
            amount_threads = max(1, int(amount_threads))
        except (TypeError, ValueError) as error:
            raise ValueError("Thread count must be a positive integer.") from error

        path_in = Path(folder).expanduser().resolve()
        path_out = Path(output).expanduser().resolve()
        if not path_in.is_dir():
            raise FileNotFoundError("Folder not found.")
        converter = ImageToVideo(str(path_in), str(path_out), output_type, transparent_webm,
                                 fps, crf, amount_threads, background_color, quality_mode, bitrate)
        frames = converter._frame_paths()
        if not frames:
            raise FileNotFoundError("No frames found in folder.")
        if len({frame.suffix.casefold() for frame in frames}) != 1:
            raise ValueError("All frames must have the same extension.")

        # Detect alpha channel in the first frame (assume all frames share same channels)
        frames_have_alpha = False
        try:
            with Image.open(frames[0]) as im:
                frames_have_alpha = "A" in im.getbands() or im.mode in ("LA", "PA")
        except (UnidentifiedImageError, OSError, IndexError):
            frames_have_alpha = False

        # Determine whether the chosen output supports alpha
        supports_alpha_out = False
        if output_type == "webm":
            supports_alpha_out = bool(transparent_webm)
        elif output_type == "apng":
            supports_alpha_out = bool(apng_transparent)
        elif output_type == "gif":
            supports_alpha_out = bool(gif_transparent)
        elif output_type == "webp":
            supports_alpha_out = bool(webp_transparent)

        use_transparency_output = frames_have_alpha and supports_alpha_out

        concat_file = converter.generate_temp_file_list()
        if not concat_file:
            raise RuntimeError("Failed to generate temporary concat file list.")

        palette_path: Optional[Path] = None
        try:
            match output_type:
                case "gif":
                    # GIF transparency support: when transparent is True, preserve alpha; otherwise composite
                    use_transparency_output = frames_have_alpha and supports_alpha_out
                    palette_command, gif_command, palette_path = converter.pre_generate_cmd_gif(
                        transparent=use_transparency_output, gif_max_colors=gif_max_colors
                    )
                    ImageToVideo._run_ffmpeg(palette_command, len(frames), progress_callback, 0, 10, abort_event, pause_event)
                    ImageToVideo._run_ffmpeg(gif_command, len(frames), progress_callback, 10, 100, abort_event, pause_event)
                case "apng":
                    ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_apng(transparent=use_transparency_output),
                                             len(frames), progress_callback, abort_event=abort_event, pause_event=pause_event)
                case "webm":
                    if converter.quality_mode == "2-pass vbr":
                        pass_log_path = os.path.join(tempfile.gettempdir(), f"ffmpeg2pass_{os.getpid()}")

                        try:
                            ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_webm(additional_arguments=["-passlogfile", pass_log_path], pass_num=1,
                                                     transparent=use_transparency_output), len(frames),
                                                     progress_callback, start_offset=0, end_offset=50, abort_event=abort_event, pause_event=pause_event)

                            ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_webm(additional_arguments=["-passlogfile", pass_log_path], pass_num=2,
                                                     transparent=use_transparency_output), len(frames),
                                                     progress_callback, start_offset=50, end_offset=100, abort_event=abort_event, pause_event=pause_event)

                        finally:
                            for ext in (".log", ".log.mbtree"):
                                log_file = pass_log_path + ext
                                try:
                                    os.remove(log_file)
                                except (FileNotFoundError, PermissionError, OSError):
                                    pass
                    else:
                        ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_webm(transparent=use_transparency_output), len(frames), progress_callback, abort_event=abort_event, pause_event=pause_event)

                case "mp4_av1" | "mp4_h264":
                    # MP4 (and other non-alpha video formats) - composite if necessary
                    if converter.quality_mode == "2-pass vbr":
                        pass_log_path = os.path.join(tempfile.gettempdir(), f"ffmpeg2pass_{os.getpid()}")

                        try:
                            ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_mp4(additional_arguments=["-passlogfile", pass_log_path], pass_num=1), len(frames),
                                                     progress_callback, start_offset=0, end_offset=50, abort_event=abort_event, pause_event=pause_event)
                            ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_mp4(additional_arguments=["-passlogfile", pass_log_path], pass_num=2), len(frames),
                                                     progress_callback, start_offset=50, end_offset=100, abort_event=abort_event, pause_event=pause_event)
                        finally:
                            for ext in (".log", ".log.mbtree"):
                                log_file = pass_log_path + ext
                                try:
                                    os.remove(log_file)
                                except (FileNotFoundError, PermissionError, OSError):
                                    pass
                    else:
                        ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_mp4(), len(frames),
                                                 progress_callback, abort_event=abort_event, pause_event=pause_event)

                case "webp":
                    ImageToVideo._run_ffmpeg(converter.pre_generate_cmd_webp(transparent=use_transparency_output), len(frames),
                                             progress_callback, abort_event=abort_event, pause_event=pause_event)
                case _:
                    raise ValueError(f"Unsupported output type: {output_type}")

            if progress_callback:
                progress_callback(100)
        finally:
            converter.cleanup()
            if palette_path is not None:
                palette_path.unlink(missing_ok=True)

    @staticmethod
    def _resolve_ffmpeg() -> str:
        """Return the FFmpeg executable that the user settings point at.

        With ``use_system_path`` enabled this is the plain ``"ffmpeg"`` name
        (resolved on PATH by subprocess). Otherwise the configured ``path`` is
        the single source of truth: it must be a directory holding ``ffmpeg`` /
        ``ffmpeg.exe`` or a direct path to the binary, and that exact file is
        returned. A clear ``FileNotFoundError`` is raised when the configured
        location does not actually provide FFmpeg, so a misconfigured path is
        never silently replaced by the system binary.
        """
        from app.settings import load_app_settings
        ffmpeg = (load_app_settings() or {}).get("ffmpeg", {}) or {}
        use_system = bool(ffmpeg.get("use_system_path", True))
        configured = str(ffmpeg.get("path") or "").strip()
        if use_system:
            return "ffmpeg"
        if not configured:
            raise FileNotFoundError(
                "ffmpeg is not configured. Set its location in Settings \u2192 FFmpeg."
            )
        if os.path.isfile(configured) and configured.lower().endswith(".exe"):
            return configured
        if os.path.isdir(configured):
            for name in ("ffmpeg.exe", "ffmpeg"):
                candidate = os.path.join(configured, name)
                if os.path.isfile(candidate):
                    return candidate
        raise FileNotFoundError(
            f"ffmpeg not found at the configured path '{configured}'. "
            "Update it in Settings \u2192 FFmpeg."
        )

    @staticmethod
    def ffmpeg_checker() -> None:
        """Raise a clear error if FFmpeg is unavailable.

        Resolves the executable from the app-level FFmpeg setting and verifies
        it responds, so a configured custom path is used exactly as stored.
        """
        cmd = ImageToVideo._resolve_ffmpeg()
        try:
            subprocess.run([cmd, "-version"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise FileNotFoundError(
                "ffmpeg not found. Please install it and try again."
            ) from error
