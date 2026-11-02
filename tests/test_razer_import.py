from pathlib import Path

import pytest

from genshin_macro.razer_import import parse_razer_xml

SAMPLE = """<Macro>
  <Name>Demo</Name>
  <MacroEvents>
    <MacroEvent><Type>actionBar</Type><recordProfile/><selected>false</selected></MacroEvent>
    <MacroEvent><Type>1</Type><KeyEvent><Makecode>16</Makecode><State>0</State></KeyEvent></MacroEvent>
    <MacroEvent><Type>0</Type><Number>0.05</Number></MacroEvent>
    <MacroEvent><Type>1</Type><KeyEvent><Makecode>16</Makecode><State>1</State></KeyEvent></MacroEvent>
    <MacroEvent><Type>0</Type><Number>0.3</Number></MacroEvent>
    <MacroEvent><Type>6</Type><Number>2</Number><LoopEvent><State>0</State></LoopEvent></MacroEvent>
    <MacroEvent><Type>2</Type><MouseEvent><MouseButton>0</MouseButton><State>0</State></MouseEvent></MacroEvent>
    <MacroEvent><Type>0</Type><Number>0.04</Number></MacroEvent>
    <MacroEvent><Type>2</Type><MouseEvent><MouseButton>0</MouseButton><State>1</State></MouseEvent></MacroEvent>
    <MacroEvent><Type>0</Type><Number>0.1</Number></MacroEvent>
    <MacroEvent><Type>6</Type><Number>2</Number><LoopEvent><State>1</State></LoopEvent></MacroEvent>
    <MacroEvent><Type>2</Type><MouseEvent><MouseButton>1</MouseButton><State>0</State></MouseEvent></MacroEvent>
    <MacroEvent><Type>0</Type><Number>0.02</Number></MacroEvent>
    <MacroEvent><Type>2</Type><MouseEvent><MouseButton>1</MouseButton><State>1</State></MouseEvent></MacroEvent>
    <MacroEvent><Type>1</Type><KeyEvent><Makecode>57421</Makecode><State>0</State></KeyEvent></MacroEvent>
    <MacroEvent><Type>1</Type><KeyEvent><Makecode>57421</Makecode><State>1</State></KeyEvent></MacroEvent>
  </MacroEvents>
  <DelaySetting>0</DelaySetting>
</Macro>"""


def test_parse_name_and_timeline():
    name, events = parse_razer_xml(SAMPLE)
    assert name == "Demo"
    assert [(e.t, e.type, e.code) for e in events[:2]] == [(0, "key_down", 16), (50, "key_up", 16)]


def test_loop_block_is_expanded_count_times():
    _, events = parse_razer_xml(SAMPLE)
    clicks = [(e.t, e.type) for e in events if e.code == "left"]
    # loop body (down, 40ms, up, 100ms) runs twice starting at t=350
    assert clicks == [(350, "mouse_down"), (390, "mouse_up"), (490, "mouse_down"), (530, "mouse_up")]


def test_right_button_and_extended_key():
    _, events = parse_razer_xml(SAMPLE)
    rights = [e for e in events if e.code == "right"]
    assert [(e.t, e.type) for e in rights] == [(630, "mouse_down"), (650, "mouse_up")]
    ext = [e for e in events if e.type.startswith("key") and e.ext]
    assert [(e.code, e.ext) for e in ext] == [(0x4D, True), (0x4D, True)]  # 0xE04D -> right arrow, extended


def test_unknown_mouse_button_and_unknown_type_are_skipped():
    xml = SAMPLE.replace("<MouseButton>1</MouseButton>", "<MouseButton>2</MouseButton>").replace("<Type>actionBar</Type>", "<Type>99</Type>")
    _, events = parse_razer_xml(xml)
    assert not any(e.code == "right" for e in events)
    assert events[0].t == 0


def test_invalid_xml_raises():
    with pytest.raises(ValueError):
        parse_razer_xml("<nope>")
    with pytest.raises(ValueError):
        parse_razer_xml("<Other/>")


REAL = Path(__file__).resolve().parent / "fixtures" / "skirk.xml"


@pytest.mark.skipif(not REAL.exists(), reason="sample file not present")
def test_real_skirk_file_imports():
    name, events = parse_razer_xml(REAL.read_text(encoding="utf-8"))
    assert name == "Skirk"
    assert len(events) == 24 + 162  # every key/mouse event in the file (Razer's own mouse up/down counts are unbalanced)
    assert sum(1 for e in events if e.type == "key_down") == sum(1 for e in events if e.type == "key_up") == 12
    assert events[-1].t == 11700  # all delays (11.91 s) minus the trailing 0.21 s wait after the last event
    assert all(events[i].t <= events[i + 1].t for i in range(len(events) - 1))
