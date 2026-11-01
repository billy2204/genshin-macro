import json
from pathlib import Path

import pytest

from genshin_macro import updater
from genshin_macro.updater import APP_VERSION, is_newer, make_swap_script, parse_manifest


def test_app_version_is_semver():
    assert len(APP_VERSION.split(".")) == 3 and all(p.isdigit() for p in APP_VERSION.split("."))


def test_is_newer_compares_numerically():
    assert is_newer("1.2.0", "1.1.9")
    assert is_newer("1.10.0", "1.9.0")
    assert not is_newer("1.1.0", "1.1.0")
    assert not is_newer("1.0.0", "1.1.0")
    assert is_newer("v2.0", "1.9.9")  # tolerant of "v" prefix / fewer parts


def test_parse_manifest_requires_version_and_url():
    v, u = parse_manifest(json.dumps({"version": "1.2.0", "url": "https://x/y.exe"}))
    assert (v, u) == ("1.2.0", "https://x/y.exe")
    with pytest.raises(ValueError):
        parse_manifest(json.dumps({"version": "1.2.0"}))
    with pytest.raises(ValueError):
        parse_manifest("not json")


def test_swap_script_waits_copies_and_relaunches(tmp_path):
    target = tmp_path / "GenshinMacro.exe"
    new = tmp_path / "new.exe"
    script = make_swap_script(pid=1234, target=target, new_exe=new)
    assert "1234" in script
    assert str(target) in script and str(new) in script
    assert "copy /y" in script.lower()
    assert 'start "" ' in script
    assert "del " in script  # cleans itself up


def test_check_for_update_uses_fetcher(monkeypatch):
    monkeypatch.setattr(updater, "_fetch_text", lambda url, timeout=10: json.dumps({"version": "9.9.9", "url": "https://x/new.exe"}))
    assert updater.check_for_update("https://x/manifest.json") == ("9.9.9", "https://x/new.exe")
    monkeypatch.setattr(updater, "_fetch_text", lambda url, timeout=10: json.dumps({"version": APP_VERSION, "url": "https://x/new.exe"}))
    assert updater.check_for_update("https://x/manifest.json") is None
