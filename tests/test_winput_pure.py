import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 only")


def test_label_for_known_scan_codes():
    from genshin_macro.winput import label_for

    assert label_for(0x3E, False).upper() == "F4"
    assert label_for(0x21, False).upper() == "F"
    assert label_for(0x1D, True)  # right ctrl, extended – any non-empty label
    assert label_for(0x1D, True) != label_for(0x1D, False)


def test_label_for_unknown_scan_falls_back():
    from genshin_macro.winput import label_for

    assert label_for(0x1FF, False) == "SC511"


def test_win32_output_implements_output_protocol():
    from genshin_macro.winput import MAGIC, Win32Output

    out = Win32Output()
    for name in ("key_down", "key_up", "mouse_down", "mouse_up"):
        assert callable(getattr(out, name))
    assert MAGIC == 0x47534D43


def test_mouse_flag_lookup():
    from genshin_macro.winput import MOUSE_FLAGS

    assert MOUSE_FLAGS[("left", True)] == 0x0002
    assert MOUSE_FLAGS[("left", False)] == 0x0004
    assert MOUSE_FLAGS[("right", True)] == 0x0008
    assert MOUSE_FLAGS[("right", False)] == 0x0010
