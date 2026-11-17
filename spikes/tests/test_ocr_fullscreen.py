from spikes.ocr.fullscreen import line_match


def test_line_match_finds_best_line_for_each_expected():
    expected = ["Then, Sotheby.", "AUTO"]
    got = ["AUTO", "Then, Sotheby", "noise"]
    result = line_match(expected, got)
    assert result[0] == ("Then, Sotheby.", "Then, Sotheby", 1 / 14)
    assert result[1] == ("AUTO", "AUTO", 0.0)


def test_line_match_expected_inside_longer_ocr_line():
    # OCR may merge "Druvis III:" and the sentence on the same row into one line
    result = line_match(["Then, Sotheby."], ["Druvis III: Then, Sotheby."])
    assert result[0][2] == 0.0


def test_line_match_missing_line_is_full_error():
    assert line_match(["Hello"], []) == [("Hello", "", 1.0)]
