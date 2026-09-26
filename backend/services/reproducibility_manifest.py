from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import platform
import shutil
import stat
import subprocess
from collections.abc import Iterable
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from backend.core.paths import confine_path


def _windows_artifact_entry(path: Path, root: Path, entry: dict) -> dict:
    """Validate the opened Windows object, then read only that same handle."""
    import msvcrt
    from ctypes import wintypes

    class FileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation", wintypes.FILETIME),
            ("access", wintypes.FILETIME),
            ("write", wintypes.FILETIME),
            ("volume", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    final_path = kernel32.GetFinalPathNameByHandleW
    final_path.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final_path.restype = wintypes.DWORD
    file_info = kernel32.GetFileInformationByHandle
    file_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(FileInformation)]
    file_info.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = wintypes.BOOL

    # OPEN_EXISTING follows reparse points, but the path is not trusted until
    # GetFinalPathNameByHandleW checks the object actually opened.
    handle = create_file(str(path), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        if error in (2, 3):
            return entry
        cause = ctypes.WinError(error)
        raise ValueError("artifact_path is outside configured safe directories") from cause
    try:
        length = final_path(handle, None, 0, 0)
        if not length or length > 32767:
            raise ValueError("cannot verify manifest artifact handle path")
        buffer = ctypes.create_unicode_buffer(length + 1)
        count = final_path(handle, buffer, len(buffer), 0)
        if not count or count >= len(buffer):
            raise ValueError("cannot verify manifest artifact handle path")
        opened = buffer.value
        if opened.startswith("\\\\?\\UNC\\"):
            opened = "\\\\" + opened[8:]
        elif opened.startswith("\\\\?\\"):
            opened = opened[4:]
        else:
            raise ValueError("cannot verify manifest artifact handle path")
        opened = os.path.normcase(os.path.normpath(opened))
        allowed = os.path.normcase(os.path.normpath(root))
        try:
            within_root = os.path.commonpath((opened, allowed)) == allowed
        except ValueError:
            within_root = False
        if not within_root:
            raise ValueError("artifact_path is outside configured safe directories")

        info = FileInformation()
        if not file_info(handle, ctypes.byref(info)):
            raise ValueError("cannot inspect manifest artifact handle")
        entry["exists"] = True
        if info.attributes & 0x10:  # FILE_ATTRIBUTE_DIRECTORY
            return entry

        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handle = None  # CRT now owns the handle.
        try:
            file = os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise
        h = hashlib.sha256()
        with file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                h.update(chunk)
        entry.update(
            {"size_bytes": (info.size_high << 32) | info.size_low, "sha256": h.hexdigest()}
        )
        return entry
    finally:
        if handle is not None:
            close_handle(handle)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def binary_version(name: str) -> dict:
    path = shutil.which(name)
    if not path:
        return {"available": False, "path": None, "version": None}
    try:
        proc = subprocess.run(
            [path, "-version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
            check=False,
        )
        version = proc.stdout.splitlines()[0] if proc.stdout else None
    except Exception:
        logging.getLogger("backend").warning("Unable to determine %s version", name, exc_info=True)
        version = "unavailable"
    return {"available": True, "path": path, "version": version}


def _artifact_entry(path: Path, root: Path) -> dict:
    """Inspect a validated path through a pinned, verified handle."""
    entry = {"path": str(path), "exists": False}
    if os.name == "nt":
        return _windows_artifact_entry(path, root, entry)
    relative = path.relative_to(root)
    parts = relative.parts
    # Never fall back to path-based reads on hosts without descriptor-relative,
    # no-follow opens: a symlink swap after validation would read outside root.
    if not (os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")):
        raise ValueError("secure manifest artifact inspection is unavailable on this platform")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        try:
            directory_fd = os.open(root, directory_flags)
            stack.callback(os.close, directory_fd)
            for part in parts[:-1]:
                directory_fd = os.open(part, directory_flags, dir_fd=directory_fd)
                stack.callback(os.close, directory_fd)
            if not parts:
                info = os.fstat(directory_fd)
                entry["exists"] = True
                return entry
            fd = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
            )
            stack.callback(os.close, fd)
        except FileNotFoundError:
            return entry
        except OSError as exc:
            raise ValueError("artifact_path is outside configured safe directories") from exc

        info = os.fstat(fd)
        entry["exists"] = True
        if stat.S_ISREG(info.st_mode):
            h = hashlib.sha256()
            duplicate = os.dup(fd)
            try:
                file = os.fdopen(duplicate, "rb")
            except BaseException:
                os.close(duplicate)
                raise
            with file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    h.update(chunk)
            entry.update({"size_bytes": info.st_size, "sha256": h.hexdigest()})
    return entry


def build_reproducibility_manifest(
    *,
    workflow: str,
    settings: dict,
    artifacts: Iterable[Path],
    artifact_roots: Iterable[Path],
    dataset: dict | None = None,
) -> dict:
    roots = tuple(
        (Path(root), confine_path(root, root, allow_root=True)) for root in artifact_roots
    )
    entries = []
    for artifact in artifacts:
        for root, canonical_root in roots:
            try:
                path = confine_path(artifact, root, allow_root=True)
            except ValueError:
                continue
            entries.append(_artifact_entry(path, canonical_root))
            break
        else:
            raise ValueError("artifact_path is outside configured safe directories")
    return {
        "manifest_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "workflow": workflow,
        "dataset": dataset or {},
        "settings": settings,
        "artifacts": entries,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "external_binaries": {n: binary_version(n) for n in ("ffmpeg", "exiftool", "colmap")},
    }
