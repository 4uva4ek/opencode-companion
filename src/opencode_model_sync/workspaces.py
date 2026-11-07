"""Workspaces: the folders opencode works in, plus the git worktrees attached to them.

opencode keeps them in its own database and shows them in its sidebar. Rows for folders that are gone
stay in the list, and opencode has no screen to clean them up, so this page offers two ways out:
excluding a workspace hides it in this app only, removing it asks opencode itself to drop it.

The running opencode service is preferred, through ``opencode api``, because it owns the data: it
removes a worktree with the strategy it was created with and reconciles its own state. When the
service is not running the same rows are read straight from the database, which stays read-only there.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from collections.abc import Mapping
from urllib.parse import quote

from .config import config_dir
from .i18n import tr

STATE_NAME = "model-sync-workspaces.json"
PROJECT = "project"
WORKTREE = "worktree"


class WorkspaceError(Exception):
    """A workspace cannot be read or changed."""


class ForceRequired(WorkspaceError):
    """opencode refuses to remove a worktree that holds changes of its own."""


@dataclass
class Workspace:
    project_id: str
    directory: str
    kind: str
    strategy: str | None = None
    archived: bool = False
    sessions: int = 0
    active: int = 0
    project_dir: str = ""
    can_remove: bool = True

    @property
    def key(self) -> str:
        return normalize(self.directory)

    @property
    def name(self) -> str:
        return Path(self.directory).name or self.directory

    @property
    def exists(self) -> bool:
        return Path(self.directory).is_dir()

    @property
    def is_git(self) -> bool:
        return self.strategy == "git" or (Path(self.directory) / ".git").exists()

    @property
    def last_used(self) -> str:
        if not self.active:
            return ""
        return datetime.fromtimestamp(self.active / 1000).strftime("%Y-%m-%d %H:%M")


def normalize(directory: str) -> str:
    """A path compared without caring about separators, case or a trailing slash."""
    path = str(directory).replace("\\", "/").rstrip("/")
    return path.casefold() if os.name == "nt" else path


def project_id(directory: str) -> str:
    """The ID opencode gives a folder that is not a clone of a known repository."""
    return hashlib.sha1(f"directory:{directory}".encode()).hexdigest()


# ---- what this app hides on its own ----


def state_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("OPENCODE_MODEL_SYNC_STATE"):
        return Path(env["OPENCODE_MODEL_SYNC_STATE"])
    return config_dir(env) / STATE_NAME


def read_excluded(path: Path | None = None) -> set[str]:
    path = path or state_path()
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    items = data.get("excluded") if isinstance(data, dict) else None
    return {normalize(item) for item in items} if isinstance(items, list) else set()


def write_excluded(keys: set[str], path: Path | None = None) -> None:
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"excluded": sorted(keys)}, indent=2, ensure_ascii=False) + "\n"
    path.write_text(body, encoding="utf-8")


def exclude(workspace: Workspace, path: Path | None = None) -> set[str]:
    keys = read_excluded(path)
    keys.add(workspace.key)
    write_excluded(keys, path)
    return keys


def include(workspace: Workspace, path: Path | None = None) -> set[str]:
    keys = read_excluded(path)
    keys.discard(workspace.key)
    write_excluded(keys, path)
    return keys


# ---- talking to opencode ----


def api(cli: Path, method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
    """One request to the running opencode service through its command line."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = [str(cli), "api", method, path]
    if body is not None:
        command += ["--data", json.dumps(body)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=flags,
        check=False,
    )
    text = (result.stdout or "").strip()
    payload: Any = None
    if text.startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
    if result.returncode != 0:
        raise _error(payload, result.stderr)
    if isinstance(payload, dict) and payload.get("_tag"):
        raise _error(payload, "")
    return payload


def _error(payload: Any, stderr: str) -> WorkspaceError:
    """The message opencode sends back, in the shape of an error of ours."""
    data = payload.get("data") or {} if isinstance(payload, dict) else {}
    message = str(data.get("message") or "") or stderr.strip()
    if isinstance(payload, dict) and payload.get("_tag") == "WorktreeError" and data.get("forceRequired"):
        return ForceRequired(message or tr("error.forceRequired"))
    return WorkspaceError(message or tr("error.opencodeFailed"))


def database_path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path | None:
    """Where opencode keeps its database, or None when it has none yet."""
    env = os.environ if env is None else env
    home = home or Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
    candidates = []
    if env.get("OPENCODE_STORAGE"):
        candidates.append(Path(env["OPENCODE_STORAGE"]) / "opencode.db")
    base = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else home / ".local" / "share"
    candidates.append(base / "opencode" / "opencode.db")
    candidates.append(home / "Library" / "Application Support" / "opencode" / "opencode.db")
    if env.get("APPDATA"):
        candidates.append(Path(env["APPDATA"]) / "opencode" / "opencode.db")
    if env.get("LOCALAPPDATA"):
        candidates.append(Path(env["LOCALAPPDATA"]) / "opencode" / "opencode.db")
    return next((path for path in candidates if path.is_file()), None)


def _connect(path: Path, readonly: bool = True) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else ""), uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    # Table names are internal constants, never values from a database row or user input.
    return {row["name"] for row in connection.execute(f'pragma table_info("{table}")')}


def _usage(connection: sqlite3.Connection) -> tuple[dict[str, int], dict[str, int]]:
    """Read the v2 session table, or empty counts when the database predates it."""
    if not {"project_id", "directory"} <= _columns(connection, "session_v2"):
        return {}, {}
    by_project = {row["project_id"]: row["total"] for row in connection.execute(
        "select project_id, count(*) as total from session_v2 group by project_id"
    )}
    by_directory = {normalize(row["directory"]): row["total"] for row in connection.execute(
        "select directory, count(*) as total from session_v2 group by directory"
    ) if row["directory"]}
    return by_project, by_directory


def _rows(connection: sqlite3.Connection) -> list[Workspace]:
    by_project, by_directory = _usage(connection)
    columns = _columns(connection, "project")
    times = [name for name in ("time_active", "time_updated", "time_created") if name in columns]
    active = "coalesce(" + ", ".join([*times, "0"]) + ")" if times else "0"
    archived = "time_archived" if "time_archived" in columns else "null"
    can_archive = {"time_archived", "time_updated"} <= columns
    found: dict[str, Workspace] = {}
    for row in connection.execute(
        f"select id, worktree, {active} as active, {archived} as archived from project"
    ):
        directory = str(row["worktree"])
        found[normalize(directory)] = Workspace(
            project_id=str(row["id"]),
            directory=directory,
            kind=PROJECT,
            archived=row["archived"] is not None,
            sessions=by_directory.get(normalize(directory), by_project.get(str(row["id"]), 0)),
            active=int(row["active"]),
            can_remove=can_archive,
        )
    by_id = {item.project_id: item for item in found.values()}
    worktree_columns = _columns(connection, "worktree")
    if worktree_columns:
        strategy = "strategy" if "strategy" in worktree_columns else "null"
        rows = connection.execute(f"select project_id, directory, {strategy} as strategy from worktree")
        trees = [(str(row["project_id"]), str(row["directory"]), row["strategy"], True) for row in rows]
    else:
        # A database without a worktree table has no worktrees to list.
        trees = []
    for ident, directory, strategy, can_remove in trees:
        key = normalize(directory)
        if key in found:
            continue
        project = by_id.get(ident)
        found[key] = Workspace(
            project_id=ident,
            directory=directory,
            kind=WORKTREE,
            strategy=strategy,
            sessions=by_directory.get(key, 0),
            active=project.active if project else 0,
            project_dir=project.directory if project else "",
            can_remove=can_remove,
        )
    return sorted(found.values(), key=lambda item: (-item.active, item.name.lower()))


def list_from_database(path: Path) -> list[Workspace]:
    try:
        connection = _connect(path, readonly=True)
    except sqlite3.Error as error:
        raise WorkspaceError(tr("error.database", error=error)) from error
    try:
        return _rows(connection)
    except sqlite3.Error as error:
        raise WorkspaceError(tr("error.database", error=error)) from error
    finally:
        connection.close()


def list_from_service(cli: Path) -> list[Workspace]:
    """Projects and their worktrees as the running service sees them, sessions from its database."""
    counts: tuple[dict[str, int], dict[str, int]] = ({}, {})
    database = database_path()
    if database:
        try:
            connection = _connect(database, readonly=True)
            counts = _usage(connection)
            connection.close()
        except sqlite3.Error:
            counts = ({}, {})
    by_project, by_directory = counts
    found: dict[str, Workspace] = {}
    for project in api(cli, "GET", "/api/project?archived=true") or []:
        directory = str(project.get("canonical") or "")
        if not directory:
            continue
        ident = str(project.get("id") or "")
        active = int((project.get("time") or {}).get("active") or 0)
        found[normalize(directory)] = Workspace(
            project_id=ident,
            directory=directory,
            kind=PROJECT,
            archived=bool((project.get("time") or {}).get("archived")),
            sessions=by_directory.get(normalize(directory), by_project.get(ident, 0)),
            active=active,
        )
    for workspace in list(found.values()):
        for row in api(cli, "GET", "/api/worktree?projectID=" + quote(workspace.project_id)) or []:
            directory = str(row.get("directory") or "")
            key = normalize(directory)
            if not directory or key in found:
                continue
            found[key] = Workspace(
                project_id=workspace.project_id,
                directory=directory,
                kind=WORKTREE,
                strategy=row.get("strategy"),
                sessions=by_directory.get(key, 0),
                active=workspace.active,
                project_dir=workspace.directory,
            )
    return sorted(found.values(), key=lambda item: (-item.active, item.name.lower()))


def list_workspaces(cli: Path | None) -> tuple[list[Workspace], str]:
    """The workspaces and a note about where they came from: the service, or its database."""
    if cli:
        try:
            return list_from_service(cli), tr("workspaces.note.service")
        except (WorkspaceError, OSError, ValueError, subprocess.SubprocessError):
            pass
    database = database_path()
    if not database:
        return [], tr("workspaces.note.none")
    return list_from_database(database), tr("workspaces.note.database")


# ---- changes ----


def add(cli: Path | None, directory: str) -> Workspace:
    """Hand a folder to opencode; it registers it as a workspace, as when a folder is opened there."""
    path = Path(directory).expanduser()
    if not path.is_dir():
        raise WorkspaceError(tr("error.notAFolder", folder=path))
    if not cli:
        raise WorkspaceError(tr("error.noService"))
    target = str(path.absolute())
    api(cli, "GET", "/api/location?location[directory]=" + quote(target))
    return Workspace(project_id=project_id(target), directory=target, kind=PROJECT)


def remove(workspace: Workspace, cli: Path | None, force: bool = False) -> str:
    """Drop a workspace the way opencode does, and say which way that turned out to be."""
    if not workspace.can_remove:
        raise WorkspaceError(tr("error.workspaceSchema"))
    if workspace.kind == WORKTREE:
        refused: WorkspaceError | None = None
        if cli:
            try:
                api(
                    cli,
                    "DELETE",
                    "/api/worktree",
                    {"projectID": workspace.project_id, "directory": workspace.directory, "force": force},
                )
                return "banner.wsRemovedByOpencode"
            except ForceRequired:
                raise  # opencode wants to be asked twice, and it is in a better position to answer than we are
            except WorkspaceError as error:
                # A folder that is gone leaves a row opencode can no longer reach. Its work can
                # not be lost by removing the row, which is the only way to clear such a stuck entry.
                refused = error
                if workspace.exists:
                    raise
        if not _forget_worktree(workspace) and refused:
            raise refused  # nothing of ours was deleted, so the answer of opencode is the whole story
        return "banner.wsForgotten"
    _archive_project(workspace)
    return "banner.wsArchived"


def unarchive(workspace: Workspace) -> None:
    """Put a workspace back on the list of opencode: the archive mark is the only thing hiding it."""
    database = _writable("project", {"id", "time_archived", "time_updated"})
    try:
        database.execute(
            "update project set time_archived = null, time_updated = ? where id = ? and time_archived is not null",
            (_now(), workspace.project_id),
        )
        database.commit()
    finally:
        database.close()


def _forget_worktree(workspace: Workspace) -> bool:
    """Remove the saved pointer to a worktree without touching the folder itself; True if there was one.

    A path is served the way a path is spelled on its system while opencode keeps it in its
    database with forward slashes, so the row is looked for by its normalised form and deleted
    under the spelling it is actually stored with.
    """
    database = _writable("worktree", {"project_id", "directory"})
    forgotten = False
    try:
        wanted = normalize(workspace.directory)
        stored = database.execute(
            "select directory from worktree where project_id = ?", (workspace.project_id,)
        ).fetchall()
        for row in stored:
            if normalize(row[0]) != wanted:
                continue
            database.execute(
                "delete from worktree where project_id = ? and directory = ?", (workspace.project_id, row[0])
            )
            forgotten = True
        database.commit()
    finally:
        database.close()
    return forgotten


def _archive_project(workspace: Workspace) -> None:
    """Mark the project as archived, which is how opencode takes it off its own list."""
    database = _writable("project", {"id", "time_archived", "time_updated"})
    try:
        database.execute(
            "update project set time_archived = ?, time_updated = ? where id = ? and time_archived is null",
            (_now(), _now(), workspace.project_id),
        )
        database.commit()
    finally:
        database.close()


def _now() -> int:
    """The moment in whole milliseconds, the unit of every time column of opencode. Its own
    reader refuses a row with a fraction in it, so nothing else may be written here."""
    return int(datetime.now().timestamp() * 1000)


def _writable(table: str, required: set[str]) -> sqlite3.Connection:
    database = database_path()
    if not database:
        raise WorkspaceError(tr("error.noDatabase"))
    connection = _connect(database, readonly=True)
    try:
        if not required <= _columns(connection, table):
            raise WorkspaceError(tr("error.workspaceSchema"))
    finally:
        connection.close()
    _backup(database)
    return _connect(database, readonly=False)


def _backup(database: Path) -> None:
    """Keep a copy of the database before the first write of this run, as the config writer does."""
    global _backed_up
    if _backed_up:
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = database.with_name(f"{database.name}.bak-model-sync-{stamp}")
    with _connect(database, readonly=True) as source, sqlite3.connect(target) as copy:
        source.backup(copy)
    _backed_up = True


_backed_up = False


def reset_backup() -> None:
    """Forget the backup was taken; used by tests and after a failed write."""
    global _backed_up
    _backed_up = False
