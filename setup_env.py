"""Bootstrap the contributor development environment for this project.

Creates the project virtualenv (default ``.venv``) and then installs or
updates the packages declared in ``requirements.txt``.

Examples
--------
    python setup_env.py                  create/update everything needed
    python setup_env.py --check          report only, change nothing
    python setup_env.py --recreate       rebuild the virtualenv from scratch
    python setup_env.py --python py-3.13 force a specific base interpreter
"""

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys

MIN_PYTHON = (3, 10)
REQUIREMENTS_NAME = "requirements.txt"
VENV_DIR_NAME = ".venv"
IS_WINDOWS = platform.system() == "Windows"


def project_root():
    return os.path.dirname(os.path.abspath(__file__))


def log(message, prefix="[*]"):
    print(f"{prefix} {message}", flush=True)


def run_command(cmd, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"command failed:\n{' '.join(cmd)}")
    return result


def run_capture(cmd):
    result = run_command(cmd)
    return result.stdout.strip()


def venv_python(venv_dir):
    if IS_WINDOWS:
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def interpreter_version(cmd):
    version = run_capture([*cmd, "-c", "import sys;print('%d.%d.%d'%sys.version_info[:3])"])
    return tuple(int(part) for part in version.split(".")[:3])


def interpreter_ok(cmd):
    try:
        version = interpreter_version(cmd)
    except (OSError, RuntimeError):
        return None
    if version < (3,):
        return None
    return version


def is_venv_interpreter(interpreter):
    exe_dir = os.path.dirname(interpreter)
    for candidate in (exe_dir, os.path.dirname(exe_dir)):
        if os.path.isfile(os.path.join(candidate, "pyvenv.cfg")):
            return True
    return False


def find_base_interpreter():
    candidates = []
    if sys.executable and not is_venv_interpreter(sys.executable):
        candidates.append([sys.executable])
    if IS_WINDOWS:
        for minor in ("13", "12", "11", "10"):
            candidates.append(["py", f"-3.{minor}"])
        candidates.append(["py", "-3"])
    else:
        candidates.append(["python3"])
    candidates.append(["python"])

    seen_versions = set()
    for command in candidates:
        version = interpreter_ok(command)
        if version is None:
            continue
        if version in seen_versions:
            continue
        seen_versions.add(version)
        if version >= MIN_PYTHON:
            return command
    return None


def resolve_base_interpreter(raw_value):
    command = shlex.split(raw_value)
    version = interpreter_ok(command)
    if version is None:
        raise SystemExit(f"cannot run/identify Python interpreter: {raw_value}")
    if version < MIN_PYTHON:
        raise SystemExit(f"Python {'.'.join(map(str, version))} is too old; need >= 3.10")
    return raw_value, command


def check_version(python):
    version = interpreter_version([python])
    if version < MIN_PYTHON:
        raise SystemExit(
            f"Python {'.'.join(map(str, version))} is too old; the project needs >= 3.10."
        )


def ensure_pip(python):
    probe = subprocess.run([python, "-m", "pip", "--version"], capture_output=True, text=True)
    if probe.returncode != 0:
        log("pip is missing, bootstrapping it with ensurepip.")
        run_command([python, "-m", "ensurepip", "--upgrade"])


def create_venv(base_command, venv_dir):
    run_command([*base_command, "-m", "venv", venv_dir])
    python = venv_python(venv_dir)
    log("Ensuring a current pip inside the virtualenv.")
    run_command([python, "-m", "pip", "install", "--upgrade", "pip"])
    return python


def pending_changes(python, requirements):
    cmd = [
        python,
        "-m",
        "pip",
        "install",
        "--dry-run",
        "--upgrade",
        "--quiet",
        "--report",
        "-",
        "-r",
        requirements,
    ]
    output = run_capture(cmd)
    report = json.loads(output)
    return report.get("install", [])


def install_requirements(python, requirements):
    cmd = [python, "-m", "pip", "install", "--upgrade", "-r", requirements]
    run_command(cmd)


def describe_changes(changes):
    return [
        item.get("metadata", {}).get("name", "?") + "==" + item.get("metadata", {}).get("version", "?")
        for item in changes
    ]


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would change without modifying anything",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="delete the existing virtualenv and build it from scratch",
    )
    parser.add_argument(
        "--python",
        default=None,
        metavar="COMMAND",
        help="base interpreter to build the virtualenv from (e.g. py -3.13 or a full path)",
    )
    parser.add_argument(
        "--venv",
        default=os.path.join(project_root(), VENV_DIR_NAME),
        metavar="DIR",
        help="virtualenv directory (default: %(default)s)",
    )
    parser.add_argument(
        "--requirements",
        default=os.path.join(project_root(), REQUIREMENTS_NAME),
        metavar="FILE",
        help="requirements file (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    venv_dir = os.path.abspath(args.venv)
    requirements = os.path.abspath(args.requirements)
    python = venv_python(venv_dir)

    if not os.path.isfile(requirements):
        raise SystemExit(f"requirements file not found: {requirements}")

    if args.recreate and os.path.isdir(venv_dir):
        log(f"Removing existing virtualenv at {venv_dir}.")
        shutil.rmtree(venv_dir)

    if not os.path.exists(python):
        log(f"No virtualenv found at {venv_dir}.")
        if args.check:
            log("Nothing to do (--check).")
            return
        if args.python:
            raw_value, base_command = resolve_base_interpreter(args.python)
            log(f"Using requested interpreter: {raw_value}")
        else:
            base_command = find_base_interpreter()
            if base_command is None:
                raise SystemExit(
                    "no suitable Python interpreter found (need 3.10+); "
                    "install Python 3.10+ or pass --python."
                )
            log(f"Using interpreter: {' '.join(base_command)}")
        log(f"Creating virtualenv at {venv_dir}.")
        python = create_venv(base_command, venv_dir)
    else:
        log(f"Virtualenv found at {venv_dir}.")

    check_version(python)
    ensure_pip(python)

    log("Checking dependencies against " + os.path.basename(requirements) + ".")
    changes = pending_changes(python, requirements)

    if not changes:
        log("All dependencies are already up to date.")
        return

    log("Outdated or missing packages:")
    for label in describe_changes(changes):
        log("  " + label, "  ")

    if args.check:
        log("Run `python setup_env.py` to apply these changes.")
        return

    log(f"Installing {len(changes)} package(s).")
    install_requirements(python, requirements)
    log("Done. Start the app with:")
    log("  " + venv_python(venv_dir), "  ")
    log("  " + '"<venv-python>" main.py', "  ")
    log("or simply: python main.py", "  ")


if __name__ == "__main__":
    main()