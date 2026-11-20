"""Settings → Model rows: shared/fixtures/model_catalog (Kotlin ModelCatalog.kt passes them too)."""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from app.model_catalog import catalog

FIX = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "model_catalog"


@pytest.mark.parametrize("case", json.loads((FIX / "catalog.json").read_text(encoding="utf-8")), ids=lambda c: c["name"])
def test_catalog(case):
    got = catalog(case["manifest"], case["installed"], case["bundled"], case["active"])
    assert [asdict(r) for r in got] == case["rows"]
