"""FFmpeg binary discovery: PATH scan plus common install roots."""

import os
import shutil

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
