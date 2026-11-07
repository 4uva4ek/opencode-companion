"""Build a standalone app for the current OS with PyInstaller.

    uv run python scripts/build.py

Produces dist/OpenCode Companion(.app|.exe folder) and an archive next to it named
opencode-companion-<os>-<arch>.(zip|tar.gz). Each OS has to build its own app.
"""

from __future__ import annotations

import os
import hashlib
import json
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "OpenCode Companion"
SLUG = "opencode-companion"


def build_environment(environ=None) -> dict[str, str]:
    """Do not let unrelated SDKs on PATH supply identically named Windows DLLs."""
    env = dict(os.environ if environ is None else environ)
    if sys.platform == "win32":
        windows = Path(env.get("SystemRoot", r"C:\Windows"))
        env["PATH"] = os.pathsep.join(dict.fromkeys(map(str, (
            Path(sys.executable).parent, Path(sys.base_prefix), windows / "System32", windows,
        ))))
    return env


def validate_windows_qt(bundle: Path) -> None:
    """Reject bundled ICU lookalikes that lack the symbols required by QtCore."""
    import pefile

    with pefile.PE(str(bundle / "_internal" / "PySide6" / "Qt6Core.dll")) as qt:
        imports = next((item for item in qt.DIRECTORY_ENTRY_IMPORT if item.dll.lower() == b"icuuc.dll"), None)
        if imports is None:
            return
        required = {item.name for item in imports.imports if item.name}
    # System ICU is normally excluded by PyInstaller. If an ICU is bundled,
    # validate every copy: Windows can load only one DLL with this base name.
    for library in bundle.rglob("*"):
        if library.name.lower() != "icuuc.dll":
            continue
        with pefile.PE(str(library)) as pe:
            exported = {item.name for item in pe.DIRECTORY_ENTRY_EXPORT.symbols if item.name}
        missing = required - exported
        if missing:
            raise RuntimeError(f"Incompatible ICU in {library}: missing {', '.join(x.decode() for x in sorted(missing))}")


def smoke_app(executable: Path, directory: Path) -> None:
    """Exercise the frozen app on every OS; Windows also uses its native Qt plugin."""
    report = directory / f"{target()}-smoke.json"
    report.unlink(missing_ok=True)
    env = build_environment()
    env["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
    # Developer Qt/Python overrides must not hide a missing packaged dependency.
    for name in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    result = subprocess.run([str(executable), "--self-test", str(report)], env=env,
                            timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    data = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    if result.returncode or data.get("status") != "ok":
        raise RuntimeError(f"Frozen application smoke test failed: {data or result.returncode}")
    print(f"Executable verified: Qt {data['qt']}, platform {data['platform']}")


def render_icon(path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "src"))
    from PySide6.QtGui import QGuiApplication

    from opencode_model_sync.icons import logo

    app = QGuiApplication.instance() or QGuiApplication([])
    logo().pixmap(512, 512).save(str(path))
    del app


def target() -> str:
    system = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)
    return f"{system}-{arch}"


def released_version() -> str:
    """The number the release is named by, taken from the file that decides it."""
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def stamp_version(app: Path, version: str) -> None:
    """Write the release number into the bundle, where macOS reads it back.

    PyInstaller is told the app's name, icon and identifier but never its number, so a finished
    bundle says 0.0.0: the About panel, `defaults read` of an installed copy and any comparison
    against a published release all read a version that was never released. Both keys are written,
    because macOS shows the first and version comparisons elsewhere read the second.
    """
    info = app / "Contents" / "Info.plist"
    with info.open("rb") as stream:
        data = plistlib.load(stream)
    data["CFBundleShortVersionString"] = version
    data["CFBundleVersion"] = version
    with info.open("wb") as stream:
        plistlib.dump(data, stream)


def resign_macos(app: Path) -> None:
    """Sign the bundle again, badly on purpose: writing into it broke the signature PyInstaller put
    on it, and an ad-hoc signature is what a build made on a machine nobody owns can honestly have."""
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)


def archive_macos(app: Path, archive: Path) -> None:
    """Preserve bundle symlinks and verify the archive users will download."""
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)],
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="model-sync-archive-") as directory:
        subprocess.run(["ditto", "-x", "-k", str(archive), directory], check=True)
        restored = Path(directory) / app.name
        for original in app.rglob("*"):
            relative = original.relative_to(app)
            extracted = restored / relative
            if original.is_symlink():
                if not extracted.is_symlink() or extracted.readlink() != original.readlink():
                    raise RuntimeError(f"Archive did not preserve symlink: {relative}")
                if not extracted.exists():
                    raise RuntimeError(f"Archive contains a broken symlink: {relative}")
        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(restored)], check=True
        )


def write_checksum(archive: Path) -> Path:
    """The archive's digest, in the form every checksum tool on every system reads.

    Written as bytes on purpose. Text mode on Windows turns the line feed into CRLF, and the verifier
    then goes looking for a file whose name ends in a carriage return - it reports the published
    archive as missing, although the digits beside it are right. The 0.7.1 Windows archive shipped
    with exactly that file.
    """
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    path = archive.with_name(archive.name + ".sha256")
    path.write_bytes(f"{digest}  {archive.name}\n".encode("ascii"))
    return path


def main() -> None:
    if sys.platform == "win32":
        os.environ["PATH"] = build_environment()["PATH"]
    icon = ROOT / "assets" / "icon.png"
    icon.parent.mkdir(exist_ok=True)
    render_icon(icon)

    dist = ROOT / "dist"
    # Keep older builds and archives. PyInstaller replaces only this app's target.
    dist.mkdir(exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name",
            NAME,
            "--icon",
            str(icon),
            "--osx-bundle-identifier",
            "dev.opencode-companion",
            "--paths",
            str(ROOT / "src"),
            "--add-data",
            f"{ROOT / 'src' / 'opencode_model_sync' / 'settings_schema.json'}{os.pathsep}opencode_model_sync",
            # QtNetwork supplies the local socket used to activate the running instance.
            "--exclude-module",
            "PySide6.QtQml",
            "--exclude-module",
            "PySide6.QtQuick",
            "--exclude-module",
            "PySide6.QtPdf",
            str(ROOT / "src" / "opencode_model_sync" / "__main__.py"),
        ],
        check=True,
        cwd=ROOT,
        env=build_environment(),
    )

    version = released_version()
    if sys.platform == "win32":
        validate_windows_qt(dist / NAME)
        smoke_app(dist / NAME / f"{NAME}.exe", ROOT / "build")
    elif sys.platform == "darwin":
        app = dist / f"{NAME}.app"
        # PyInstaller never hears the number, so the finished bundle would say 0.0.0: the About
        # panel of an installed copy, `defaults read`, and anyone comparing an installed app with a
        # published release would all read a version that was never released. Writing the plist
        # invalidates the signature PyInstaller put on it, so it gets signed again afterwards.
        stamp_version(app, version)
        resign_macos(app)
        smoke_app(app / "Contents" / "MacOS" / NAME, ROOT / "build")
    else:
        smoke_app(dist / NAME / NAME, ROOT / "build")

    archive_base = dist / f"{SLUG}-{target()}"
    if sys.platform == "darwin":
        archive = f"{archive_base}.zip"
        archive_macos(dist / f"{NAME}.app", Path(archive))
    elif sys.platform == "win32":
        archive = shutil.make_archive(str(archive_base), "zip", dist, NAME)
    else:
        archive = f"{archive_base}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(dist / NAME, arcname=SLUG)
    archive_path = Path(archive)
    write_checksum(archive_path)
    print(f"built {archive_path.name} for {version}")


if __name__ == "__main__":
    main()
