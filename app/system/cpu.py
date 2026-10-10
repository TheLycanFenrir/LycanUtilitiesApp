"""CPU detection: core counts and model/name discovery."""

import os
import platform
import subprocess


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
            import winreg

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
