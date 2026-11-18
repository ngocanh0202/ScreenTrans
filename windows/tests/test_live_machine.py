import json
from pathlib import Path

import pytest

from app.live.machine import Action, LiveMachine, LiveParams

FIXTURES = sorted((Path(__file__).parents[2] / "shared" / "fixtures" / "live").glob("*.json"))


def run(data):
    m = LiveMachine(LiveParams(**data.get("params", {})))
    actions = []
    for ev in data["events"]:
        if "diff" in ev:
            a = m.on_frame(ev["t"], ev["diff"])
            if a is not Action.WAIT:
                actions.append({"t": ev["t"], "action": a.value})
        elif "ocr_text" in ev:
            actions.append({"t": ev["t"], "action": m.on_text(ev["t"], ev["ocr_text"])})
        elif ev.get("overlay_changed"):
            m.on_overlay_changed()
    return actions


def test_fixture_set_present():
    assert len(FIXTURES) >= 8


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert run(data) == data["expected"]


def test_next_delay_follows_state():
    m = LiveMachine(LiveParams())
    assert m.next_delay_ms() == 300
    m.on_frame(0, 50.0)
    assert m.state == "changing" and m.next_delay_ms() == 100
