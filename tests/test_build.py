"""Exercise macOS release packaging with real directory and file symlinks."""

import importlib.util
import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("build_app", Path(__file__).parents[1] / "scripts/build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_windows_build_does_not_search_unrelated_path(monkeypatch):
    monkeypatch.setattr(build.sys, "platform", "win32")
    original = {"PATH": r"C:\external-sdk\poppler;C:\external-sdk\libheif", "SystemRoot": r"C:\Windows", "KEEP": "value"}
    clean = build.build_environment(original)
    assert "external-sdk" not in clean["PATH"]
    assert str(Path(original["SystemRoot"]) / "System32") in clean["PATH"]
    assert clean["KEEP"] == "value"
    assert original["PATH"].startswith(r"C:\external-sdk")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PE DLLs")
def test_windows_bundle_rejects_wrong_icu_even_when_filename_matches(tmp_path):
    import PySide6
    qt = Path(PySide6.__file__).parent / "Qt6Core.dll"
    target = tmp_path / "_internal" / "PySide6"
    target.mkdir(parents=True)
    shutil.copyfile(qt, target / qt.name)
    # With no bundled ICU, Windows resolves its own system implementation.
    build.validate_windows_qt(tmp_path)
    # An unrelated PE DLL with this name must fail validation before release.
    shutil.copyfile(Path(sys.base_prefix) / "python3.dll", target.parent / "icuuc.dll")
    with pytest.raises(RuntimeError, match="Incompatible ICU"):
        build.validate_windows_qt(tmp_path)


def test_a_built_bundle_carries_the_number_the_release_is_named_by(tmp_path):
    """PyInstaller is never told the version, so the finished bundle has to be told afterwards."""
    contents = (tmp_path / "Example.app" / "Contents")
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleExecutable": "example", "CFBundleShortVersionString": "0.0.0",
                       "CFBundleVersion": "0.0.0"}, stream)
    build.stamp_version(tmp_path / "Example.app", build.released_version())
    with (contents / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert info["CFBundleShortVersionString"] == build.released_version()
    assert info["CFBundleVersion"] == build.released_version()
    assert info["CFBundleExecutable"] == "example", "nothing else in the plist may move"


def test_the_checksum_file_names_the_archive_the_way_a_verifier_reads_it(tmp_path):
    """A line feed here is not style: on Windows it became part of the named file's spelling."""
    archive = tmp_path / "app.zip"
    archive.write_bytes(b"contents")
    said = build.write_checksum(archive)
    written = said.read_bytes()
    assert b"\r" not in written, "a carriage return is read as the last letter of the file's name"
    digest = hashlib.sha256(b"contents").hexdigest()
    assert written == f"{digest}  app.zip\n".encode("ascii")


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS ditto and codesign")
def test_macos_archive_preserves_bundle_links(tmp_path):
    app = tmp_path / "Example.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Frameworks/python3__dot__12/lib-dynload").mkdir(parents=True)
    (contents / "Frameworks/python3.12").symlink_to("python3__dot__12")
    (contents / "Resources").mkdir()
    (contents / "Resources/module").symlink_to("../Frameworks/python3.12/lib-dynload/module")
    (contents / "Info.plist").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>example</string>
<key>CFBundleIdentifier</key><string>dev.test.model-sync</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>""")
    source = tmp_path / "main.c"
    source.write_text("int main(void) { return 0; }")
    subprocess.run(["cc", str(source), "-o", str(contents / "MacOS/example")], check=True)
    subprocess.run(["cc", "-dynamiclib", str(source), "-o", str(contents / "Frameworks/python3__dot__12/lib-dynload/module")], check=True)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    archive = tmp_path / "example.zip"
    build.archive_macos(app, archive)
    assert archive.is_file()
