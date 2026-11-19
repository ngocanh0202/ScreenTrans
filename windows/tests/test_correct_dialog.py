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


LONG = [Segment("text", "Ms. Z, please walk Madam Constantine through this section.",
                 "Cô Z, hãy dẫn Phu nhân Constantine qua phần này.", (0, 0, 400, 20))]


def click(qtbot, picker, i, shift=False):
    from PySide6.QtCore import Qt

    qtbot.mouseClick(picker, Qt.LeftButton, Qt.ShiftModifier if shift else Qt.NoModifier, picker.word_rect(i).center())


def test_pick_words_then_keep_them(qtbot):
    d = CorrectDialog(LONG)
    qtbot.addWidget(d)
    d.show()
    picker = d.pickers[0]
    click(qtbot, picker, 4)
    assert picker.selection() == "Madam"
    click(qtbot, picker, 5, shift=True)
    assert picker.selection() == "Madam Constantine" and "Madam Constantine" in d.selected_label.text()
    d.keep_button.click()
    assert d.parsed_terms() == [("Madam Constantine", None)] and picker.selection() == ""


def test_drag_over_words_then_fix_the_translation(qtbot):
    from PySide6.QtCore import Qt

    d = CorrectDialog(LONG)
    qtbot.addWidget(d)
    d.show()
    picker = d.pickers[0]
    qtbot.mousePress(picker, Qt.LeftButton, pos=picker.word_rect(0).center())
    qtbot.mouseMove(picker, picker.word_rect(1).center())
    qtbot.mouseRelease(picker, Qt.LeftButton, pos=picker.word_rect(1).center())
    assert picker.selection() == "Ms. Z"  # the comma after "Z" is not part of the term
    d.fixed_button.click()  # no Vietnamese typed yet: nothing added
    assert d.parsed_terms() == []
    d.target.setText("  Cô Z ")
    d.fixed_button.click()
    assert d.parsed_terms() == [("Ms. Z", "Cô Z")] and d.target.text() == ""


def test_remove_a_term_and_add_a_suggested_name(qtbot):
    d = CorrectDialog(LONG)
    qtbot.addWidget(d)
    d.show()
    suggested = [d.suggestions.item(i).data(256) for i in range(d.suggestions.count())]
    assert suggested == ["Madam Constantine"]
    d.add_suggestion(d.suggestions.item(0))
    assert d.parsed_terms() == [("Madam Constantine", None)] and d.suggestions.count() == 0
    d.remove_term(d.term_list.item(0))
    assert d.parsed_terms() == []


def test_enter_in_the_fixed_translation_adds_the_term_and_keeps_the_dialog_open(qtbot):  # review I1
    from PySide6.QtCore import Qt

    d = CorrectDialog(LONG)
    qtbot.addWidget(d)
    d.show()
    picker = d.pickers[0]
    click(qtbot, picker, 5)
    d.target.setFocus()
    d.target.setText("Hằng")  # (QTest cannot type non-Latin-1 characters)
    qtbot.keyClick(d.target, Qt.Key_Return)
    assert d.parsed_terms() == [("Constantine", "Hằng")] and d.isVisible() and d.result() == 0
