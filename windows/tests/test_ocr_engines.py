import math

from app.ocr import engines
from app.ocr.rapid import lines_from_rapid


def test_rapid_fragments_on_one_row_become_one_line():
    result = [([[200, 10], [300, 10], [300, 40], [200, 40]], "you going?", 0.9),
              ([[10, 12], [190, 12], [190, 42], [10, 42]], "Where are", 0.9),
              ([[10, 80], [200, 80], [200, 110], [10, 110]], "Next line.", 0.9)]
    lines = lines_from_rapid(result)
    assert [l.text for l in lines] == ["Where are you going?", "Next line."]
    assert (lines[0].left, lines[0].right) == (10, 300) and lines[0].angle == 0


def test_rapid_tilted_box_becomes_a_tilted_line():
    a = math.radians(15)
    p0 = (100, 100)
    p1 = (100 + 300 * math.cos(a), 100 + 300 * math.sin(a))
    p2 = (p1[0] - 30 * math.sin(a), p1[1] + 30 * math.cos(a))
    p3 = (p0[0] - 30 * math.sin(a), p0[1] + 30 * math.cos(a))
    (line,) = lines_from_rapid([([p0, p1, p2, p3], "At the moment", 0.9)])
    assert abs(line.angle - 15) < 0.1 and abs(line.width - 300) < 0.5 and abs(line.height - 30) < 0.5


def test_engine_registry_names_and_availability():
    assert [e.name for e in engines.WINDOWS] == ["windows", "rapid"]
    assert engines.available("windows") is True
    assert isinstance(engines.available("rapid"), bool)
    assert engines.available("nope") is False
