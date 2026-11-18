from app.gui.correct_dialog import Correction, CorrectDialog, parse_terms
from app.pipeline import Segment

SEGS = [Segment("name", "Druvis III", None, (0, 0, 10, 10)),
        Segment("text", "Hello.", "Xin chào.", (0, 20, 100, 40)),
        Segment("text", "Bye.", "Tạm biệt.", (0, 50, 100, 70))]


def test_only_changed_sentences_are_returned(qtbot):
    d = CorrectDialog(SEGS)
    qtbot.addWidget(d)
    assert len(d.edits) == 2  # names are not translated: nothing to correct
    d.edits[0].setText("Chào!")
    d.edits[1].setText("  ")  # emptied: ignored, never an empty translation
    assert d.corrections() == [Correction("Hello.", "Xin chào.", "Chào!")]


def test_terms_keep_or_map():
    assert parse_terms("Arcanist =\nVertin = Vertin\n\nno equals sign\n = x\nStorm = Bão") == [
        ("Arcanist", None), ("Vertin", "Vertin"), ("Storm", "Bão")]


def test_terms_field_is_read(qtbot):
    d = CorrectDialog(SEGS)
    qtbot.addWidget(d)
    d.terms.setPlainText("Arcanist =")
    assert d.parsed_terms() == [("Arcanist", None)]
