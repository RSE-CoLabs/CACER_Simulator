"""Utilities for building, serving, and deploying the MkDocs documentation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import urlopen
import contextlib
import io
import os
import platform
import subprocess
import sys
import time
import webbrowser


REPO_ROOT = Path(__file__).resolve().parents[1]
MKDOCS_CONFIG = REPO_ROOT / "documentation" / "mkdocs.yml"
LOCAL_SITE_DIR = REPO_ROOT / "documentation" / "site"
MKDOCS_COMMAND = [sys.executable, "-m", "mkdocs"]
_LOCAL_DOCS_PROCESS = None


def _run_mkdocs(args):
    """Run MkDocs and fall back to the in-process CLI if the Python launcher is broken."""
    result = subprocess.run(MKDOCS_COMMAND + args, cwd=REPO_ROOT, text=True, capture_output=True)
    launcher_error = "Unable to create process" in (result.stderr or result.stdout)
    if result.returncode == 0 or not launcher_error:
        return result

    try:
        from mkdocs.__main__ import cli
    except ImportError:
        return result

    stdout = io.StringIO()
    stderr = io.StringIO()
    returncode = 0
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            cli(args=args, prog_name="mkdocs", standalone_mode=False)
        except SystemExit as exc:
            returncode = int(exc.code or 0)
        except Exception as exc:
            returncode = 1
            print(exc, file=stderr)
    return SimpleNamespace(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def _pids_using_port(port):
    """Return process IDs that are listening on the selected TCP port."""
    system = platform.system().lower()

    if system == "windows":
        result = subprocess.run(["netstat", "-ano"], text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Unable to inspect local TCP ports.")

        pids = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == "TCP":
                local_address = parts[1]
                state = parts[3].upper()
                pid = parts[4]
                if local_address.endswith(f":{port}") and state == "LISTENING" and pid.isdigit():
                    pids.add(int(pid))
        return sorted(pids)

    result = subprocess.run(["lsof", "-ti", f"tcp:{port}"], text=True, capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "Unable to inspect local TCP ports.")
    return sorted({int(pid) for pid in result.stdout.split() if pid.isdigit()})


def free_localhost_port(port=8000, timeout=10, force=True):
    """Release a local TCP port used by a previous documentation server."""
    global _LOCAL_DOCS_PROCESS

    if _LOCAL_DOCS_PROCESS is not None and _LOCAL_DOCS_PROCESS.poll() is None:
        _LOCAL_DOCS_PROCESS.terminate()
        try:
            _LOCAL_DOCS_PROCESS.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _LOCAL_DOCS_PROCESS.kill()
            _LOCAL_DOCS_PROCESS.wait(timeout=timeout)

    current_pid = os.getpid()
    pids = [pid for pid in _pids_using_port(port) if pid != current_pid]

    for pid in pids:
        if platform.system().lower() == "windows":
            command = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                command.append("/F")
        else:
            command = ["kill", "-9" if force else "-15", str(pid)]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Unable to stop process {pid} on port {port}: {message}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pids_using_port(port):
            print(f"Port {port} is free.")
            return pids
        time.sleep(0.3)

    raise TimeoutError(f"Port {port} is still occupied after {timeout} seconds.")


def run_local_documentation(host="127.0.0.1", port=8000, open_browser=True, rebuild=True, release_port=True):
    """Build and serve the MkDocs documentation locally from a notebook cell."""
    global _LOCAL_DOCS_PROCESS

    if not MKDOCS_CONFIG.exists():
        raise FileNotFoundError(f"MkDocs configuration not found: {MKDOCS_CONFIG}")

    if rebuild:
        build = _run_mkdocs(["build", "-f", str(MKDOCS_CONFIG)])
        if build.stdout:
            print(build.stdout)
        if build.stderr:
            print(build.stderr)
        if build.returncode != 0:
            raise RuntimeError("MkDocs build failed. Check the output above.")

    if release_port:
        free_localhost_port(port=port)

    server_command = [
        sys.executable,
        "-m",
        "http.server",
        str(port),
        "--bind",
        host,
        "--directory",
        str(LOCAL_SITE_DIR),
    ]
    _LOCAL_DOCS_PROCESS = subprocess.Popen(
        server_command,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    url = f"http://{host}:{port}/"
    deadline = time.time() + 10
    while time.time() < deadline:
        if _LOCAL_DOCS_PROCESS.poll() is not None:
            raise RuntimeError("The local documentation server stopped during startup.")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    break
        except URLError:
            time.sleep(0.3)
    else:
        raise TimeoutError(f"The local documentation server did not respond at {url}")

    if open_browser:
        webbrowser.open(url)

    print(f"Local documentation available at: {url}")
    print("To stop it, run: free_localhost_port(port=port)")
    return _LOCAL_DOCS_PROCESS


def deploy_github_pages(remote_name="origin", remote_branch="gh-pages", assume_yes=False):
    """Build and deploy the MkDocs site to GitHub Pages."""
    if not MKDOCS_CONFIG.exists():
        raise FileNotFoundError(f"MkDocs configuration not found: {MKDOCS_CONFIG}")

    remote = subprocess.run(
        ["git", "remote", "get-url", remote_name],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    if remote.returncode != 0:
        raise RuntimeError(f"Git remote not found: {remote_name}")

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    if status.stdout.strip():
        print("Repository has local changes. They are not committed by this function:")
        print(status.stdout)

    build = _run_mkdocs(["build", "-f", str(MKDOCS_CONFIG)])
    if build.stdout:
        print(build.stdout)
    if build.stderr:
        print(build.stderr)
    if build.returncode != 0:
        raise RuntimeError("MkDocs build failed. Deploy cancelled.")

    remote_url = remote.stdout.strip()
    if not assume_yes:
        answer = input(
            f"Deploy documentation to {remote_url} on branch {remote_branch}? Type 'yes' to continue: "
        )
        if answer.strip().lower() != "yes":
            print("Deploy cancelled.")
            return None

    deploy_args = [
        "gh-deploy",
        "-f",
        str(MKDOCS_CONFIG),
        "--remote-name",
        remote_name,
        "--remote-branch",
        remote_branch,
        "--force",
    ]
    deploy = _run_mkdocs(deploy_args)
    if deploy.stdout:
        print(deploy.stdout)
    if deploy.stderr:
        print(deploy.stderr)
    if deploy.returncode != 0:
        raise RuntimeError("GitHub Pages deploy failed. Check the output above.")

    print(f"GitHub Pages deployed to branch '{remote_branch}' on remote '{remote_name}'.")
    return deploy
