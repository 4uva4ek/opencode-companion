"""Official release discovery, verified downloads and staged desktop updates."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .network import tls_context

from .version import VERSION

REPOSITORY = "4uva4ek/opencode-model-sync"
RELEASES = f"https://github.com/{REPOSITORY}/releases"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_DOWNLOAD = 1024 * 1024 * 1024


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"Unsupported release version: {value}")
    return tuple(map(int, match.groups()))


def asset_name(system: str | None = None, machine: str | None = None) -> str:
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    os_name = {"darwin": "macos", "win32": "windows", "linux": "linux"}.get(system)
    if not arch or not os_name:
        raise ValueError(f"Unsupported platform: {system}/{machine}")
    return f"opencode-companion-{os_name}-{arch}.{'tar.gz' if system == 'linux' else 'zip'}"


def request(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={
        "User-Agent": f"OpenCode-Companion/{VERSION}", "Accept": "application/vnd.github+json",
    }), timeout=30, context=tls_context())


@dataclass(frozen=True)
class Release:
    version: str
    asset: str
    url: str
    digest: str | None
    checksum_url: str | None


def parse_release(data: dict, current: str = VERSION, asset: str | None = None) -> Release | None:
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data["tag_name"]
    if version_tuple(tag) <= version_tuple(current):
        return None
    name = asset or asset_name()
    assets = {item["name"]: item for item in data.get("assets", [])}
    if name not in assets:
        raise ValueError(f"Release {tag} has no build for this computer ({name}).")
    url = f"{RELEASES}/download/{tag}/{name}"
    digest = assets[name].get("digest")
    if digest and not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Unsupported release checksum")
    checksum = url + ".sha256" if name + ".sha256" in assets else None
    if not digest and not checksum:
        raise ValueError("This release has no SHA-256 checksum; automatic installation is unavailable.")
    return Release(tag.lstrip("v"), name, url, digest, checksum)


def check() -> Release | None:
    with request(API) as response:
        return parse_release(json.loads(response.read(2 * 1024 * 1024)))


def download(release: Release, destination: Path) -> None:
    expected = release.digest.removeprefix("sha256:") if release.digest else None
    if expected is None:
        with request(release.checksum_url) as response:
            expected = response.read(4096).decode("ascii").split()[0]
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid SHA-256 checksum")
    digest = hashlib.sha256()
    total = 0
    try:
        with request(release.url) as response, destination.open("xb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise ValueError("Update archive is too large")
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != expected:
            raise ValueError("Update checksum mismatch")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def installation_root() -> Path:
    if not getattr(sys, "frozen", False):
        raise ValueError("Automatic installation is available in the packaged app. Update source checkouts with Git.")
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        root = executable.parent.parent.parent
        if root.suffix != ".app":
            raise ValueError("Cannot locate the installed macOS application bundle")
        return root
    return executable.parent


def extract(archive: Path, destination: Path, system: str) -> Path:
    """Reject escaping archive paths before extraction; preserve macOS bundle symlinks."""
    destination.mkdir()
    if system == "linux":
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter="data")
        root = destination / "opencode-companion"
    else:
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename or ":" in info.filename:
                    raise ValueError("Unsafe update archive path")
                if stat.S_ISLNK(info.external_attr >> 16):
                    if system != "darwin":
                        raise ValueError("Unexpected archive symlink")
                    target = bundle.read(info).decode("utf-8")
                    resolved = (destination / str(path.parent) / target).resolve()
                    if not resolved.is_relative_to(destination.resolve()):
                        raise ValueError("Unsafe update archive symlink")
            if system == "darwin":
                subprocess.run(["ditto", "-x", "-k", str(archive), str(destination)], check=True)
            else:
                bundle.extractall(destination)
        root = destination / ("OpenCode Companion.app" if system == "darwin" else "OpenCode Companion")
    executable = root / ("Contents/MacOS/OpenCode Companion" if system == "darwin" else
                         "OpenCode Companion.exe" if system == "win32" else "OpenCode Companion")
    if not executable.is_file() or not executable.resolve().is_relative_to(root.resolve()):
        raise ValueError("Update archive is missing the application")
    if system == "darwin":
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(root)], check=True)
    return root


@dataclass(frozen=True)
class Prepared:
    directory: Path
    staged: Path
    target: Path
    backup: Path


def prepare(release: Release) -> Prepared:
    target = installation_root()
    directory = Path(tempfile.mkdtemp(prefix=".companion-update-", dir=target.parent))
    try:
        archive = directory / release.asset
        download(release, archive)
        staged = extract(archive, directory / "unpacked", sys.platform)
        return Prepared(directory, staged, target, directory / "previous")
    except Exception:
        shutil.rmtree(directory)
        raise


def installer_script(plan: Prepared, pid: int, system: str) -> str:
    if system == "win32":
        def quote(path):
            return "'" + str(path).replace("'", "''") + "'"
        return f'''$ErrorActionPreference = 'Stop'
try {{
    Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue
    if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ throw 'Application did not exit' }}
    Move-Item -LiteralPath {quote(plan.target)} -Destination {quote(plan.backup)}
    try {{ Move-Item -LiteralPath {quote(plan.staged)} -Destination {quote(plan.target)} }}
    catch {{ Move-Item -LiteralPath {quote(plan.backup)} -Destination {quote(plan.target)}; throw }}
    Start-Process -FilePath {quote(plan.target / 'OpenCode Companion.exe')}
}} catch {{ $_ | Out-File -LiteralPath {quote(plan.directory / 'error.log')}; exit 1 }}
'''
    q = shlex.quote
    launch = (f"open {q(str(plan.target))}" if system == "darwin" else
              f"{q(str(plan.target / 'OpenCode Companion'))} >/dev/null 2>&1 &")
    return f'''#!/bin/sh
set -eu
exec 2>{q(str(plan.directory / 'error.log'))}
count=0
while kill -0 {pid} 2>/dev/null; do
    count=$((count + 1))
    [ "$count" -lt 120 ] || exit 1
    sleep 1
done
mv {q(str(plan.target))} {q(str(plan.backup))}
if ! mv {q(str(plan.staged))} {q(str(plan.target))}; then
    mv {q(str(plan.backup))} {q(str(plan.target))}
    exit 1
fi
{launch}
'''


def launch_installer(plan: Prepared) -> None:
    windows = sys.platform == "win32"
    script = plan.directory / ("install.ps1" if windows else "install.sh")
    script.write_text(installer_script(plan, os.getpid(), sys.platform), encoding="utf-8-sig" if windows else "utf-8")
    if windows:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         cwd=plan.directory)
    else:
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, cwd=plan.directory,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
