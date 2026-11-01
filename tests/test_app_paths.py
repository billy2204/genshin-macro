"""Where the app keeps macros.json / settings.json, and migration from the old
'next to the exe' location."""
import sys
from pathlib import Path

import pytest

from genshin_macro import app


def test_data_dir_from_source_is_project_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert app.data_dir() == Path(app.__file__).resolve().parents[1]


def test_data_dir_frozen_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    d = app.data_dir()
    assert d == tmp_path / "GenshinMacro"
    assert d.is_dir()  # created on demand


def test_migrate_legacy_copies_files_next_to_exe_once(tmp_path):
    exe_dir = tmp_path / "exe"
    data = tmp_path / "data"
    exe_dir.mkdir()
    data.mkdir()
    (exe_dir / "macros.json").write_text('{"random_ms": 5, "macros": []}', encoding="utf-8")
    (exe_dir / "settings.json").write_text('{"update_url": "x"}', encoding="utf-8")
    app.migrate_legacy(exe_dir, data)
    assert (data / "macros.json").read_text(encoding="utf-8").startswith('{"random_ms": 5')
    assert (data / "settings.json").exists()
    # existing files in the data dir are never overwritten
    (exe_dir / "macros.json").write_text("NEW", encoding="utf-8")
    app.migrate_legacy(exe_dir, data)
    assert "NEW" not in (data / "macros.json").read_text(encoding="utf-8")


def test_migrate_legacy_noop_when_same_dir_or_missing(tmp_path):
    app.migrate_legacy(tmp_path, tmp_path)  # same dir: nothing to do, no error
    app.migrate_legacy(tmp_path / "nope", tmp_path)  # missing source: no error
