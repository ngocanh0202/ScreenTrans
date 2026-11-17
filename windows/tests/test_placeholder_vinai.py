from pathlib import Path

import pytest

from app.glossary import Glossary
from app.translate.ct2 import Ct2Translator

REPO = Path(__file__).parents[2]
VINAI = REPO / "models" / "out" / "vinai-en2vi-ct2"
SENTS = [
    "Good morning, Timekeeper.",
    "Vertin, the storm is coming again.",
    "Sonetto smiled. \"I will follow you, Timekeeper.\"",
    "She said she was going to talk to Madam Z about it.",
    "Druvis III looked at the doll on the carpet.",
    "Then, Sonetto.",
    "Vertin and Sonetto left the suitcase behind.",
    "Your HP is low and your ATK is high.",
    "Ask Madam Z where Vertin went.",
    "The Timekeeper must find Druvis III before noon.",
]


@pytest.mark.local
def test_placeholder_survives_vinai():
    if not (VINAI / "screentrans_model.json").is_file():
        pytest.skip("vinai CT2 model not exported")
    g = Glossary.load(REPO / "shared/glossary/games/reverse1999.json", REPO / "shared/glossary/common.json")
    protected = [g.protect(s) for s in SENTS]
    outs = Ct2Translator(VINAI).translate([p for p, _ in protected])
    restored = [g.restore(o, v) for o, (_, v) in zip(outs, protected)]
    assert sum(r is not None for r in restored) >= 9
