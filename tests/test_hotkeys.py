from genshin_macro.hotkeys import HotkeyManager


class Foreground:
    def __init__(self):
        self.app = False

    def __call__(self):
        return self.app


def _make():
    fg = Foreground()
    return HotkeyManager(fg), fg


def test_fires_once_per_physical_press():
    hm, _ = _make()
    calls = []
    hm.bind(66, False, lambda: calls.append(1))
    hm.on_key(66, False, True)
    hm.on_key(66, False, True)  # auto-repeat
    hm.on_key(66, False, True)
    hm.on_key(66, False, False)
    hm.on_key(66, False, True)
    assert len(calls) == 2


def test_inert_when_app_foreground():
    hm, fg = _make()
    calls = []
    hm.bind(66, False, lambda: calls.append(1))
    fg.app = True
    hm.on_key(66, False, True)
    hm.on_key(66, False, False)
    assert calls == []
    fg.app = False
    hm.on_key(66, False, True)
    assert len(calls) == 1


def test_unbound_key_ignored():
    hm, _ = _make()
    calls = []
    hm.bind(66, False, lambda: calls.append(1))
    hm.on_key(67, False, True)
    hm.on_key(66, True, True)  # same scan, extended flag differs
    assert calls == []
    assert hm.is_bound(66, False) and not hm.is_bound(67, False)


def test_rebind_replaces_callback_and_clear_unbinds():
    hm, _ = _make()
    a, b = [], []
    hm.bind(66, False, lambda: a.append(1))
    hm.bind(66, False, lambda: b.append(1))
    hm.on_key(66, False, True)
    hm.on_key(66, False, False)
    assert (a, b) == ([], [1])
    hm.clear()
    hm.on_key(66, False, True)
    assert b == [1]
    assert not hm.is_bound(66, False)
