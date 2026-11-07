"""Workspaces: reading opencode's list, hiding rows here, and asking opencode to drop them."""
import hashlib
import json
import os
import sqlite3
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QCheckBox,
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
)
from opencode_model_sync import window, workspaces, workspaces_view  # noqa: E402


def make_database(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        create table project (
            id text primary key, worktree text, time_created integer, time_updated integer,
            time_active integer, time_archived integer
        );
        create table worktree (project_id text, directory text, strategy text);
        create table session_v2 (id text primary key, project_id text, directory text);
        """
    )
    connection.executemany(
        "insert into project values (?,?,?,?,?,?)",
        [
            ("p1", "C:/work/app", 10, 30, 30, None),
            ("p2", "C:/work/gone", 10, 20, 20, 99),
        ],
    )
    connection.executemany(
        "insert into worktree values (?,?,?)",
        [
            ("p1", "C:/work/app", None),
            ("p1", "C:/work/.wt/feature", "git"),
            ("p2", "C:/work/gone/.wt/stale", "git"),
        ],
    )
    connection.executemany(
        "insert into session_v2 (id, project_id, directory) values (?,?,?)",
        [("s1", "p1", "C:/work/app"), ("s2", "p1", "C:/work/app"), ("s3", "p2", "C:/work/gone/.wt/stale")],
    )
    connection.commit()
    connection.close()


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """A database of our own, so the opencode of this computer is neither read nor written."""
    folder = tmp_path / "storage"
    folder.mkdir()
    make_database(folder / "opencode.db")
    monkeypatch.setenv("OPENCODE_STORAGE", str(folder))
    workspaces.reset_backup()
    return folder


@pytest.fixture
def nowhere(tmp_path, monkeypatch):
    """No opencode anywhere: not its database, not its command line."""
    for variable in ("OPENCODE_STORAGE", "APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, str(tmp_path / "absent"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "absent"))


def test_the_database_lists_projects_and_their_worktrees(storage):
    items = workspaces.list_from_database(storage / "opencode.db")
    by_directory = {item.directory: item for item in items}

    assert set(by_directory) == {"C:/work/app", "C:/work/gone", "C:/work/.wt/feature", "C:/work/gone/.wt/stale"}
    assert by_directory["C:/work/app"].kind == workspaces.PROJECT
    assert by_directory["C:/work/.wt/feature"].kind == workspaces.WORKTREE
    assert by_directory["C:/work/.wt/feature"].project_dir == "C:/work/app"
    assert by_directory["C:/work/app"].sessions == 2
    assert by_directory["C:/work/gone/.wt/stale"].sessions == 1
    assert by_directory["C:/work/gone"].archived
    assert not by_directory["C:/work/app"].archived
    # The most recently used first, and a worktree right below the folder it came from.
    assert [item.directory for item in items] == [
        "C:/work/app",
        "C:/work/.wt/feature",
        "C:/work/gone",
        "C:/work/gone/.wt/stale",
    ]


def test_the_list_falls_back_to_the_database_and_says_so(storage):
    items, note = workspaces.list_workspaces(None)
    assert items
    assert note == workspaces.tr("workspaces.note.database")


def test_no_opencode_no_list(nowhere):
    assert workspaces.list_workspaces(None) == ([], workspaces.tr("workspaces.note.none"))


def test_the_folder_id_is_what_opencode_makes_of_it():
    # opencode: ID.make(Hash.fast(`directory:${directory}`)), which is the sha1 of that text.
    assert workspaces.project_id("C:\\work\\app") == hashlib.sha1(b"directory:C:\\work\\app").hexdigest()


def test_a_folder_path_matches_itself_written_another_way():
    assert workspaces.normalize("C:\\work\\app\\") == workspaces.normalize("C:/work/app")
    if os.name == "nt":
        assert workspaces.normalize("C:\\Work\\App") == workspaces.normalize("c:/work/app")


def test_excluding_writes_a_state_file_and_restoring_clears_it(tmp_path):
    state = tmp_path / "state.json"
    item = workspaces.Workspace(project_id="p1", directory="C:\\work\\.wt\\feature", kind=workspaces.WORKTREE)

    assert workspaces.read_excluded(state) == set()
    workspaces.exclude(item, state)
    assert workspaces.read_excluded(state) == {workspaces.normalize("C:/work/.wt/feature")}
    # The same folder with other separators is the same workspace.
    workspaces.exclude(
        workspaces.Workspace(project_id="p1", directory="C:/work/.wt/feature/", kind=workspaces.WORKTREE), state
    )
    assert len(workspaces.read_excluded(state)) == 1
    workspaces.include(item, state)
    assert workspaces.read_excluded(state) == set()
    assert json.loads(state.read_text(encoding="utf-8")) == {"excluded": []}


def test_a_state_file_that_is_not_ours_is_ignored(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{not json", encoding="utf-8")
    assert workspaces.read_excluded(state) == set()


def directories(connection):
    return [row[0] for row in connection.execute("select directory from worktree")]


def test_removing_a_worktree_without_the_service_forgets_the_row(storage):
    item = next(
        item for item in workspaces.list_from_database(storage / "opencode.db")
        if item.directory == "C:/work/.wt/feature"
    )
    assert workspaces.remove(item, None) == "banner.wsForgotten"

    connection = sqlite3.connect(storage / "opencode.db")
    rows = directories(connection)
    projects = connection.execute("select count(*) from project").fetchone()[0]
    connection.close()
    assert "C:/work/app" in rows and "C:/work/.wt/feature" not in rows
    assert projects == 2, "only the pointer to the worktree is gone"
    assert list(storage.glob("opencode.db.bak-model-sync-*")), "the database was not copied first"


def test_removing_a_folder_archives_it_and_keeps_the_sessions(storage):
    item = next(
        item for item in workspaces.list_from_database(storage / "opencode.db") if item.directory == "C:/work/app"
    )
    assert workspaces.remove(item, None) == "banner.wsArchived"

    connection = sqlite3.connect(storage / "opencode.db")
    archived = connection.execute("select time_archived is not null from project where id = 'p1'").fetchone()[0]
    sessions = connection.execute("select count(*) from session_v2").fetchone()[0]
    connection.close()
    assert archived == 1
    assert sessions == 3


def test_the_time_handed_to_opencode_is_whole_milliseconds(storage):
    """opencode refuses to read back a row whose time holds a fraction, so a float here breaks its API."""
    item = next(
        item for item in workspaces.list_from_database(storage / "opencode.db") if item.directory == "C:/work/app"
    )
    workspaces.remove(item, None)

    connection = sqlite3.connect(storage / "opencode.db")
    kinds, archived = connection.execute(
        "select typeof(time_archived) || '/' || typeof(time_updated), time_archived from project where id = 'p1'"
    ).fetchone()
    connection.close()
    assert kinds == "integer/integer"
    assert archived > 10**12, "milliseconds since 1970, not seconds"


def test_a_workspace_brought_out_of_the_archive_is_listed_by_opencode_again(storage):
    item = next(
        item for item in workspaces.list_from_database(storage / "opencode.db") if item.directory == "C:/work/gone"
    )
    assert item.archived

    workspaces.unarchive(item)

    connection = sqlite3.connect(storage / "opencode.db")
    archived, updated = connection.execute("select time_archived, time_updated from project where id = 'p2'").fetchone()
    untouched = connection.execute("select time_updated from project where id = 'p1'").fetchone()[0]
    connection.close()
    assert archived is None
    assert updated > 10**12, "whole milliseconds, the unit of opencode"
    assert untouched == 30, "a workspace that is not archived is left alone"


def test_removing_through_the_service_asks_opencode_and_not_the_database(storage, monkeypatch):
    seen = []

    def fake_api(cli, method, path, body=None, timeout=30.0):
        seen.append((method, path, body))
        return None

    monkeypatch.setattr(workspaces, "api", fake_api)
    item = workspaces.Workspace(project_id="p1", directory="C:/work/.wt/feature", kind=workspaces.WORKTREE)

    assert workspaces.remove(item, cli="opencode", force=True) == "banner.wsRemovedByOpencode"
    assert seen == [
        ("DELETE", "/api/worktree", {"projectID": "p1", "directory": "C:/work/.wt/feature", "force": True})
    ]
    assert list(storage.glob("opencode.db.bak-model-sync-*")) == []


def test_a_stuck_worktree_is_still_gone_when_opencode_cannot_reach_it(storage, monkeypatch):
    """The whole point of the page: a row for a folder that no longer exists."""

    def refusing(cli, method, path, body=None, timeout=30.0):
        raise workspaces.WorkspaceError("no such directory")

    monkeypatch.setattr(workspaces, "api", refusing)
    item = next(
        item for item in workspaces.list_from_database(storage / "opencode.db")
        if item.directory == "C:/work/gone/.wt/stale"
    )
    assert not item.exists

    assert workspaces.remove(item, cli="opencode") == "banner.wsForgotten"
    connection = sqlite3.connect(storage / "opencode.db")
    rows = directories(connection)
    connection.close()
    assert "C:/work/gone/.wt/stale" not in rows


def test_a_row_of_ours_is_found_whatever_way_its_path_is_spelled(storage, monkeypatch):
    """The bug of the live page: opencode serves E:\\work\\x, its database keeps E:/work/x."""

    def refusing(cli, method, path, body=None, timeout=30.0):
        raise workspaces.WorkspaceError(f"Worktree directory unavailable: {body['directory']}")

    monkeypatch.setattr(workspaces, "api", refusing)
    served = workspaces.Workspace(
        project_id="p2", directory="C:\\work\\gone\\.wt\\stale", kind=workspaces.WORKTREE, strategy="git"
    )
    assert not served.exists

    assert workspaces.remove(served, cli="opencode") == "banner.wsForgotten"
    connection = sqlite3.connect(storage / "opencode.db")
    rows = directories(connection)
    connection.close()
    assert "C:/work/gone/.wt/stale" not in rows


def test_a_refusal_with_nothing_of_ours_to_delete_is_told_and_not_glossed_over(storage, monkeypatch):
    def refusing(cli, method, path, body=None, timeout=30.0):
        raise workspaces.WorkspaceError("Worktree directory unavailable: C:/work/never/listed")

    monkeypatch.setattr(workspaces, "api", refusing)
    item = workspaces.Workspace(project_id="p2", directory="C:/work/never/listed", kind=workspaces.WORKTREE)

    with pytest.raises(workspaces.WorkspaceError, match="unavailable"):
        workspaces.remove(item, cli="opencode")


def test_opencode_being_asked_for_permission_is_not_answered_for(storage, monkeypatch):
    def refuse(cli, method, path, body=None, timeout=30.0):
        raise workspaces.ForceRequired("changes of its own")

    monkeypatch.setattr(workspaces, "api", refuse)
    item = next(
        item for item in workspaces.list_from_database(storage / "opencode.db")
        if item.directory == "C:/work/gone/.wt/stale"
    )

    with pytest.raises(workspaces.ForceRequired):
        workspaces.remove(item, cli="opencode")


def test_a_worktree_that_is_still_on_the_disk_is_not_removed_behind_opencodes_back(storage, monkeypatch, tmp_path):
    folder = tmp_path / "live-worktree"
    folder.mkdir()

    def refusing(cli, method, path, body=None, timeout=30.0):
        raise workspaces.WorkspaceError("the worktree has commits")

    monkeypatch.setattr(workspaces, "api", refusing)
    item = workspaces.Workspace(project_id="p1", directory=str(folder), kind=workspaces.WORKTREE)

    with pytest.raises(workspaces.WorkspaceError):
        workspaces.remove(item, cli="opencode")
    connection = sqlite3.connect(storage / "opencode.db")
    rows = directories(connection)
    connection.close()
    assert len(rows) == 3, "opencode refused, so its rows stay as they are"


def answer(returncode=0, stdout="", stderr=""):
    def run(command, **kwargs):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


def test_a_refusal_from_opencode_becomes_one_kind_of_error(monkeypatch):
    monkeypatch.setattr(
        workspaces.subprocess,
        "run",
        answer(1, '{"_tag":"WorktreeError","data":{"message":"dirty","forceRequired":true}}', "HTTP 400"),
    )
    with pytest.raises(workspaces.ForceRequired):
        workspaces.api("opencode", "DELETE", "/api/worktree", {})

    monkeypatch.setattr(workspaces.subprocess, "run", answer(1, "", "HTTP 500"))
    with pytest.raises(workspaces.WorkspaceError) as refused:
        workspaces.api("opencode", "GET", "/api/project")
    assert "HTTP 500" in str(refused.value)

    monkeypatch.setattr(workspaces.subprocess, "run", answer(0, "[]"))
    assert workspaces.api("opencode", "GET", "/api/project") == []


def test_adding_hands_the_folder_to_the_running_opencode(monkeypatch, tmp_path):
    folder = tmp_path / "new"
    folder.mkdir()
    asked = []

    def fake_api(cli, method, path, body=None, timeout=30.0):
        asked.append((method, path))
        return {"directory": str(folder), "project": {"id": "x"}}

    monkeypatch.setattr(workspaces, "api", fake_api)
    item = workspaces.add("opencode", str(folder))

    assert item.directory == str(folder.absolute())
    assert asked[0][0] == "GET" and asked[0][1].startswith("/api/location?location[directory]=")
    assert item.name == "new"

    with pytest.raises(workspaces.WorkspaceError):
        workspaces.add("opencode", str(tmp_path / "missing"))
    with pytest.raises(workspaces.WorkspaceError):
        workspaces.add(None, str(folder))


# ---- the page itself ----


@pytest.fixture
def view(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / "opencode.json"
    config.write_text(json.dumps({"providers": {}}))
    monkeypatch.setattr(window, "config_path", lambda: config)
    monkeypatch.setattr(window.MainWindow, "refresh", window.MainWindow._reload_config)
    monkeypatch.setenv("OPENCODE_MODEL_SYNC_STATE", str(tmp_path / "state.json"))
    items = [
        workspaces.Workspace(project_id="p1", directory=str(tmp_path / "app"), kind=workspaces.PROJECT, active=30),
        workspaces.Workspace(
            project_id="p1", directory=str(tmp_path / "gone"), kind=workspaces.WORKTREE, strategy="git", active=20
        ),
    ]
    monkeypatch.setattr(window.workspaces, "list_workspaces", lambda cli: (items, "from the test"))
    monkeypatch.setattr(window.catalog, "find_cli", lambda *a, **kw: None)

    def run(work, done, failed):
        try:
            result = work()
        except Exception as error:  # noqa: BLE001
            failed(str(error))
        else:
            done(result)

    monkeypatch.setattr(window.tasks, "run", run)
    widget = window.MainWindow()
    widget._show_tab(1)
    yield widget, items, tmp_path / "state.json"
    widget.close()
    widget.deleteLater()
    app.processEvents()


def panel(widget):
    """The page as it is now: rendering throws the previous panel away with deleteLater."""
    layout = widget.workspaces_layout
    for index in range(layout.count()):
        item = layout.itemAt(index).widget()
        if isinstance(item, workspaces_view.WorkspacesPanel):
            return item
    return None


def rows(widget):
    page = panel(widget)
    scroll = page.findChild(QScrollArea) if page else None
    if scroll is None:
        return []
    return scroll.widget().findChildren(workspaces_view.WorkspaceRow)


def listed(widget):
    return [row.item for row in rows(widget)]


def test_the_workspaces_tab_opens_with_the_list_of_opencode(view):
    widget, items, _ = view
    assert [widget.tabs.tabText(index) for index in range(widget.tabs.count())] == [
        window.tr("tab.providers"),
        window.tr("tab.workspaces"),
        window.tr("nav.agents"),
        "MCP",
        window.settings_text("title"),
    ]
    assert widget.tab == "workspaces"
    assert widget.stack.currentIndex() == 1
    assert [item.directory for item in listed(widget)] == [item.directory for item in items]
    # The providers tab still holds everything the app did before.
    assert widget.stack.widget(0).layout().indexOf(widget.sidebar) == 0
    widget._show_tab(0)
    assert widget.stack.currentIndex() == 0 and widget.tab == "providers"


def test_excluding_takes_a_row_off_this_list_only(view):
    widget, items, state = view
    gone = next(item for item in items if item.name == "gone")
    widget.exclude_workspace(gone)

    assert [item.name for item in listed(widget)] == ["app"]
    assert workspaces.read_excluded(state) == {workspaces.normalize(gone.directory)}

    check = panel(widget).findChildren(QCheckBox)[0]
    assert check.text() == window.tr("ws.showExcluded", count=1)
    check.setChecked(True)
    assert [item.name for item in listed(widget)] == ["app", "gone"]

    widget.restore_workspace(gone)
    assert workspaces.read_excluded(state) == set()
    assert len(listed(widget)) == 2


def test_a_row_offers_both_actions_and_marks_a_folder_that_is_gone(view):
    widget, items, _ = view
    row = next(row for row in rows(widget) if row.item.name == "gone")
    buttons = [child.text() for child in row.findChildren(QPushButton)]
    assert window.tr("ws.exclude") in buttons
    assert window.tr("ws.remove") in buttons
    assert window.tr("ws.missing") in [child.text() for child in row.findChildren(QLabel)]
    assert window.tr("ws.worktree") in [child.text() for child in row.findChildren(QLabel)]


def test_a_cancelled_question_starts_nothing(view, monkeypatch):
    widget, items, _ = view
    monkeypatch.setattr(window.QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    called = []
    monkeypatch.setattr(window.workspaces, "remove", lambda *a, **kw: called.append(1))

    widget.remove_workspace(next(item for item in items if item.name == "gone"))
    assert called == []
    assert not widget.ws_busy


def test_removing_a_worktree_asks_once_and_reports_what_opencode_did(view, monkeypatch):
    widget, items, _ = view
    answers = iter([QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(window.QMessageBox, "question", lambda *a, **kw: next(answers))
    calls = []

    def fake_remove(item, cli, force=False):
        calls.append(force)
        return "banner.wsRemovedByOpencode"

    monkeypatch.setattr(window.workspaces, "remove", fake_remove)
    widget.remove_workspace(next(item for item in items if item.name == "gone"))

    assert calls == [False]
    assert not widget.ws_busy


def test_a_worktree_with_changes_of_its_own_is_only_removed_after_a_second_yes(view, monkeypatch):
    widget, items, _ = view
    answers = iter([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(window.QMessageBox, "question", lambda *a, **kw: next(answers))
    calls = []

    def fake_remove(item, cli, force=False):
        calls.append(force)
        if not force:
            raise workspaces.ForceRequired("dirty")
        return "banner.wsRemovedByOpencode"

    monkeypatch.setattr(window.workspaces, "remove", fake_remove)
    widget.remove_workspace(next(item for item in items if item.name == "gone"))

    assert calls == [False, True], "the second question is what lets opencode force it"
    assert not widget.ws_busy


def test_removing_a_folder_takes_its_row_off_the_page(view, monkeypatch):
    """What the user watches for after «Remove»: the row is no longer there."""
    widget, items, _ = view
    away = workspaces.Workspace(project_id="p9", directory="E:/gone/away", kind=workspaces.PROJECT, active=5)
    items.append(away)
    widget.refresh_workspaces()
    assert "away" in [item.name for item in listed(widget)]

    def archiving(item, cli, force=False):
        item.archived = True  # what opencode leaves behind a removed folder: its row, marked archived
        return "banner.wsArchived"

    monkeypatch.setattr(window.QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(window.workspaces, "remove", archiving)
    widget.remove_workspace(away)

    assert away.archived
    assert "away" not in [item.name for item in listed(widget)], "opencode archived it, so the page lets it go"
    assert not widget.ws_busy

    check = panel(widget).findChildren(QCheckBox)[1]
    assert check.text() == window.tr("ws.showArchived", count=1)
    check.setChecked(True)
    assert "away" in [item.name for item in listed(widget)], "and it is one click away from being seen again"


def test_an_archived_row_offers_the_way_out_rather_than_removal(view, monkeypatch):
    widget, items, _ = view
    away = workspaces.Workspace(
        project_id="p9", directory="E:/gone/away", kind=workspaces.PROJECT, active=5, archived=True
    )
    items.append(away)
    widget.show_archived = True
    widget.render_workspaces()

    row = next(row for row in rows(widget) if row.item.name == "away")
    assert window.tr("ws.unarchive") in [child.text() for child in row.findChildren(QPushButton)]
    assert window.tr("ws.remove") not in [child.text() for child in row.findChildren(QPushButton)]
    assert window.tr("ws.archived") in [child.text() for child in row.findChildren(QLabel)]

    def opening(item):
        item.archived = False

    monkeypatch.setattr(window.workspaces, "unarchive", opening)
    widget.unarchive_workspace(away)

    assert not away.archived
    row = next(row for row in rows(widget) if row.item.name == "away")
    assert window.tr("ws.remove") in [child.text() for child in row.findChildren(QPushButton)]


@pytest.fixture
def v1_storage(tmp_path, monkeypatch):
    """The project/session layout in OpenCode v1.2.27's official SQL definitions."""
    database = tmp_path / "opencode.db"
    with sqlite3.connect(database) as connection:
        connection.executescript('''
            create table project (id text primary key, worktree text not null,
                time_created integer, time_updated integer, time_initialized integer,
                sandboxes text not null);
            create table session (id text primary key, project_id text, directory text);
        ''')
        connection.execute("insert into project values (?, ?, ?, ?, ?, ?)",
            ("p1", "/Users/me/app", 10, 30, None,
             json.dumps(["/Users/me/app", "/Users/me/.wt/feature", "/Users/me/.wt/feature"])))
        connection.executemany("insert into session values (?, ?, ?)", [
            ("s1", "p1", "/Users/me/app"), ("s2", "p1", "/Users/me/.wt/feature"),
            ("s3", "p1", "/Users/me/.wt/feature")])
    monkeypatch.setattr(workspaces, "database_path", lambda: database)
    workspaces.reset_backup()
    return database


def test_v1_database_lists_its_projects_with_empty_usage_and_no_writes(v1_storage):
    """A v1 database is still listed, but its sessions and sandboxes are not read."""
    before = v1_storage.read_bytes()
    items, note = workspaces.list_workspaces(None)
    assert [item.directory for item in items] == ["/Users/me/app"]
    assert items[0].kind == workspaces.PROJECT
    assert items[0].sessions == 0
    assert all(item.active == 30 and not item.archived and not item.can_remove for item in items)
    assert note == workspaces.tr("workspaces.note.database")
    assert v1_storage.read_bytes() == before
    assert not list(v1_storage.parent.glob("*.bak-*"))


@pytest.mark.parametrize("operation", [workspaces.remove, workspaces.unarchive, workspaces._forget_worktree])
def test_unsupported_v1_writes_refuse_without_modifying_database(v1_storage, operation):
    before = v1_storage.read_bytes()
    # A stale/service row may lack capability information: check the real schema before writing.
    item = workspaces.Workspace("p1", "/Users/me/app", workspaces.PROJECT)
    with pytest.raises(workspaces.WorkspaceError, match=workspaces.tr("error.workspaceSchema")):
        operation(item, None) if operation is workspaces.remove else operation(item)
    assert v1_storage.read_bytes() == before
    assert not list(v1_storage.parent.glob("*.bak-*"))


def test_v1_rows_allow_excluding_but_disable_unsupported_removal(v1_storage, view):
    widget, _, _ = view
    widget.ws_items = workspaces.list_from_database(v1_storage)
    widget.render_workspaces()
    assert len(rows(widget)) == 1
    for row in rows(widget):
        buttons = {button.text(): button for button in row.findChildren(QPushButton)}
        assert buttons[window.tr("ws.exclude")].isEnabled()
        assert not buttons[window.tr("ws.remove")].isEnabled()
        assert buttons[window.tr("ws.remove")].toolTip() == window.tr("error.workspaceSchema")


@pytest.mark.parametrize("time_columns, values, expected", [
    ("time_updated integer, time_created integer", (None, 12), 12),
    ("time_created integer", (12,), 12),
    ("", (), 0),
])
def test_missing_optional_timestamps_and_session_tables(tmp_path, time_columns, values, expected):
    database = tmp_path / "opencode.db"
    with sqlite3.connect(database) as connection:
        connection.execute("create table project (id text, worktree text" + (", " + time_columns if time_columns else "") + ")")
        params = ("p", "/app", *values)
        connection.execute("insert into project values (" + ",".join("?" for _ in params) + ")", params)
    item, = workspaces.list_from_database(database)
    assert item.active == expected
    assert item.sessions == 0
    assert not item.archived


def test_a_v1_session_table_kept_alongside_is_not_read(v1_storage):
    """v1 session rows sitting next to a v2 table are not read, so a project with none in v2 counts zero."""
    with sqlite3.connect(v1_storage) as connection:
        connection.execute("create table session_v2 (project_id text, directory text)")
    project = next(item for item in workspaces.list_from_database(v1_storage) if item.kind == workspaces.PROJECT)
    assert project.sessions == 0
