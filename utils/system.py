"""System utilities for CPU detection and resource monitoring."""

import os
import platform
import shutil
import subprocess
import winreg


def get_available_cores():
    """Get the total logical CPU cores"""
    total_cores = os.cpu_count() or 1
    return total_cores


def get_dropdown_core_options():
    """Get the dropdown options for core selection"""
    total_cores = get_available_cores()
    return [str(i) for i in range(1, total_cores + 1)]


def get_cpu_name():
    """
    Get the actual CPU model/name.

    Windows:
        Reads ProcessorNameString from the Windows Registry.

    Linux:
        Reads model name from /proc/cpuinfo.

    macOS:
        Uses sysctl hw.model / machdep.cpu.brand_string.

    Falls back to platform information if necessary.
    """

    system = platform.system()

    # --------------------------------------------------------
    # WINDOWS
    # --------------------------------------------------------
    if system == "Windows":
        try:
            key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")

                if cpu_name:
                    return " ".join(cpu_name.split())

        except (FileNotFoundError, PermissionError, OSError):
            pass

    # --------------------------------------------------------
    # LINUX
    # --------------------------------------------------------
    elif system == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        cpu_name = line.split(":", 1)[1].strip()

                        if cpu_name:
                            return cpu_name

        except (FileNotFoundError, PermissionError, OSError):
            pass

    # --------------------------------------------------------
    # MACOS
    # --------------------------------------------------------
    elif system == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=2
            )

            cpu_name = result.stdout.strip()

            if cpu_name:
                return cpu_name

        except (FileNotFoundError, PermissionError, OSError):
            pass

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------
    try:
        cpu_name = platform.processor()

        if cpu_name:
            return cpu_name

    except (AttributeError, OSError, ValueError):
        pass

    return "Unknown CPU Model"


_FFMPEG_BINARIES = ("ffmpeg.exe", "ffprobe.exe")


def detect_ffmpeg_binaries():
    """Locate FFmpeg installations on this machine.

    Scans the Windows ``PATH`` environment variable plus the standard install
    roots (Program Files, local app data, home directory) for directories that
    actually contain ``ffmpeg.exe`` or ``ffprobe.exe``.

    Returns ``{"system": bool, "dirs": [{"dir": str, "binaries": [str, ...]}]}``
    so the frontend can offer the detected directories as pickable options and
    still know whether the plain ``ffmpeg`` command resolves on PATH.
    """
    found = []
    seen = set()

    def consider(entry):
        entry = (entry or "").strip()
        if not entry:
            return
        key = os.path.normcase(os.path.normpath(entry))
        if key in seen:
            return
        seen.add(key)
        if not os.path.isdir(entry):
            return
        has = [name for name in _FFMPEG_BINARIES if os.path.isfile(os.path.join(entry, name))]
        if has:
            found.append({"dir": entry, "binaries": has})

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        consider(entry)

    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("USERPROFILE"),
    ]
    roots.append("C:\\")
    for root in roots:
        if not root:
            continue
        consider(os.path.join(root, "ffmpeg"))
        consider(os.path.join(root, "ffmpeg", "bin"))

    system_found = shutil.which("ffmpeg") is not None or shutil.which("ffprobe") is not None
    found.sort(key=lambda item: (-len(item["binaries"]), item["dir"].lower()))
    return {"system": bool(system_found), "dirs": found}
