import json

import pytest

from genshin_macro.model import (
    Config,
    InputEvent,
    KeyRef,
    RecordedMacro,
    SpamMacro,
    macro_from_dict,
    new_id,
)


def _sample_config() -> Config:
    spam = SpamMacro(
        id=new_id(),
        name="Skip story",
        hotkey=KeyRef(scan=66, ext=False, label="F8"),
        key=KeyRef(scan=33, ext=False, label="F"),
        interval_ms=80,
    )
    rec = RecordedMacro(
        id=new_id(),
        name="Combo",
        hotkey=KeyRef(scan=67, ext=False, label="F9"),
        loop=True,
        events=[
            InputEvent(t=0, type="key_down", code=18, ext=False),
            InputEvent(t=120, type="key_up", code=18, ext=False),
            InputEvent(t=300, type="mouse_down", code="left"),
            InputEvent(t=350, type="mouse_up", code="left"),
        ],
    )
    return Config(random_ms=150, macros=[spam, rec])


def test_config_roundtrip(tmp_path):
    cfg = _sample_config()
    path = tmp_path / "macros.json"
    cfg.save(path)
    loaded = Config.load(path)
    assert loaded.to_dict() == cfg.to_dict()
    assert loaded.macros[0].kind == "spam"
    assert loaded.macros[1].kind == "recorded"
    assert loaded.macros[1].events[2].code == "left"


def test_load_missing_file_returns_default(tmp_path):
    cfg = Config.load(tmp_path / "nope.json")
    assert cfg.random_ms == 100
    assert cfg.macros == []


def test_load_corrupt_file_returns_default(tmp_path):
    path = tmp_path / "macros.json"
    path.write_text("{not json", encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.random_ms == 100
    assert cfg.macros == []


def test_macro_from_dict_unknown_kind_raises():
    with pytest.raises(ValueError):
        macro_from_dict({"kind": "x", "id": "1", "name": "n"})


def test_random_ms_clamped_non_negative():
    cfg = Config.from_dict({"random_ms": -5, "macros": []})
    assert cfg.random_ms == 0


def test_save_writes_valid_json_with_version(tmp_path):
    path = tmp_path / "macros.json"
    _sample_config().save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["random_ms"] == 150
    assert len(data["macros"]) == 2


def test_record_hotkey_and_overlay_roundtrip(tmp_path):
    cfg = Config(random_ms=100, macros=[], record_hotkey=KeyRef(68, False, "F10"), overlay=False)
    path = tmp_path / "m.json"
    cfg.save(path)
    loaded = Config.load(path)
    assert loaded.record_hotkey == KeyRef(68, False, "F10")
    assert loaded.overlay is False


def test_defaults_for_record_hotkey_and_overlay():
    cfg = Config.from_dict({"random_ms": 100, "macros": []})
    assert cfg.record_hotkey is None
    assert cfg.overlay is True


def test_load_skips_bad_macro_entries_and_keeps_good_ones(tmp_path):
    path = tmp_path / "macros.json"
    good = SpamMacro(id="a", name="ok", key=KeyRef(33, False, "F")).to_dict()
    path.write_text(json.dumps({"random_ms": 50, "macros": [good, {"kind": "zzz"}, "x", {"kind": "spam", "id": "b", "name": "n", "interval_ms": "abc"}]}), encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.random_ms == 50
    assert [m.id for m in cfg.macros] == ["a"]


def test_load_non_dict_macros_does_not_crash(tmp_path):
    path = tmp_path / "macros.json"
    path.write_text(json.dumps({"macros": {"a": 1}}), encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.macros == []


def test_corrupt_file_is_backed_up_before_defaults(tmp_path):
    path = tmp_path / "macros.json"
    path.write_text("{not json", encoding="utf-8")
    Config.load(path)
    bak = tmp_path / "macros.json.bak"
    assert bak.exists() and bak.read_text(encoding="utf-8") == "{not json"
