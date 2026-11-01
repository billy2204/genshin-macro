"""MouseButtonPoller: polls button state and reports transitions (fallback when the
low-level hook does not see clicks inside a raw-input game)."""
import threading

from genshin_macro.mousepoll import VK_LBUTTON, VK_RBUTTON, MouseButtonPoller


class FakeState:
    def __init__(self):
        self.down = set()

    def __call__(self, vk):
        return vk in self.down


def test_reports_down_and_up_transitions_once():
    st, out = FakeState(), []
    p = MouseButtonPoller(st, lambda b, d: out.append((b, d)))
    p.tick()  # nothing pressed
    st.down.add(VK_RBUTTON)
    p.tick()
    p.tick()  # still held: no repeat
    st.down.remove(VK_RBUTTON)
    p.tick()
    assert out == [("right", True), ("right", False)]


def test_left_and_right_independent():
    st, out = FakeState(), []
    p = MouseButtonPoller(st, lambda b, d: out.append((b, d)))
    st.down = {VK_LBUTTON, VK_RBUTTON}
    p.tick()
    st.down = {VK_RBUTTON}
    p.tick()
    assert out == [("left", True), ("right", True), ("left", False)]


def test_buttons_already_held_at_start_are_not_reported_as_new_presses():
    st, out = FakeState(), []
    st.down = {VK_LBUTTON}
    p = MouseButtonPoller(st, lambda b, d: out.append((b, d)))
    p.tick()
    assert out == []
    st.down = set()
    p.tick()
    assert out == []  # we never saw the press, so no orphan release either


def test_thread_start_stop_runs_ticks():
    st, out = FakeState(), []
    seen = threading.Event()
    p = MouseButtonPoller(st, lambda b, d: (out.append((b, d)), seen.set()), interval_s=0.001)
    p.start()
    st.down.add(VK_RBUTTON)
    assert seen.wait(1.0)
    p.stop()
    assert out[0] == ("right", True)
    assert not p.running
