from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence
import venv


REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_VENV = REPOSITORY_ROOT / ".venv"
DEFAULT_REQUIREMENTS = REPOSITORY_ROOT / "requirements.txt"


def setup_environment(
    venv_path: Path = DEFAULT_VENV,
    requirements_file: Path = DEFAULT_REQUIREMENTS,
    *,
    install: bool = True,
    create: bool = True,
) -> Path:
    """Create, install, and validate the project virtual environment."""
    venv_path = venv_path.resolve()
    requirements_file = requirements_file.resolve()
    if not requirements_file.is_file():
        raise FileNotFoundError(
            f"Requirements file does not exist: {requirements_file}"
        )
    python_executable = environment_python(venv_path)
    if not python_executable.is_file():
        if not create:
            raise FileNotFoundError(
                f"Virtual environment does not exist: {venv_path}"
            )
        if venv_path.exists() and any(venv_path.iterdir()):
            raise RuntimeError(
                f"Environment path exists but has no Python interpreter: "
                f"{venv_path}"
            )
        venv.EnvBuilder(with_pip=True).create(venv_path)
    if install:
        subprocess.run(
            [
                str(python_executable),
                "-m",
                "pip",
                "install",
                "--requirement",
                str(requirements_file),
            ],
            check=True,
        )
    validate_environment(
        python_executable,
        venv_path,
        requirements_file,
    )
    return python_executable


def validate_environment(
    python_executable: Path,
    venv_path: Path,
    requirements_file: Path,
) -> None:
    """Verify the interpreter belongs to the venv and pins are installed."""
    command = [
        str(python_executable.resolve()),
        "-c",
        _VALIDATION_SCRIPT,
        str(venv_path.resolve()),
        str(requirements_file.resolve()),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Environment validation failed: {message}")
    subprocess.run(
        [str(python_executable), "-m", "pip", "check"],
        check=True,
    )


def environment_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and validate the CACER Simulator environment."
    )
    parser.add_argument(
        "--venv",
        type=Path,
        default=DEFAULT_VENV,
        help="Virtual environment directory (default: .venv).",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=DEFAULT_REQUIREMENTS,
        help="Pinned requirements file.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing environment without installing packages.",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        python_executable = setup_environment(
            options.venv,
            options.requirements,
            install=not options.validate_only,
            create=not options.validate_only,
        )
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Environment ready: {python_executable}")
    return 0


_VALIDATION_SCRIPT = r"""
import importlib.metadata
import json
from pathlib import Path
import re
import sys

expected_venv = Path(sys.argv[1]).resolve()
requirements_path = Path(sys.argv[2])
actual_prefix = Path(sys.prefix).resolve()
errors = []
if actual_prefix != expected_venv:
    errors.append(
        f"interpreter prefix {actual_prefix} does not match {expected_venv}"
    )

for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
    if match is None:
        errors.append(f"unsupported requirement entry: {line}")
        continue
    name, expected_version = match.groups()
    try:
        actual_version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        errors.append(f"{name} is not installed")
        continue
    if actual_version != expected_version:
        errors.append(
            f"{name}=={actual_version}, expected {expected_version}"
        )

if errors:
    raise SystemExit("; ".join(errors))
print(json.dumps({"python": sys.version, "prefix": str(actual_prefix)}))
"""


if __name__ == "__main__":
    raise SystemExit(main())
