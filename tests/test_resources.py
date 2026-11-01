import sys
from pathlib import Path

from genshin_macro import resources


def test_resource_path_from_source_points_at_project_assets(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    p = resources.resource_path("assets/icon.ico")
    assert p == Path(resources.__file__).resolve().parents[1] / "assets" / "icon.ico"
    assert p.is_file()


def test_resource_path_frozen_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resources.resource_path("assets/icon.ico") == tmp_path / "assets" / "icon.ico"


def test_icon_file_is_multi_size_ico():
    from PIL import Image

    im = Image.open(resources.resource_path("assets/icon.ico"))
    assert im.format == "ICO"
    assert (256, 256) in im.info.get("sizes", set()) and (16, 16) in im.info.get("sizes", set())
