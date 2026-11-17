import json

from app.cache import TranslationCache, normalize
from app.datalog import PairLogger


def test_normalize():
    assert normalize("  Hello \n  world ") == "Hello world"


def test_get_after_put_with_normalized_key():
    c = TranslationCache(10, None)
    c.put("m", "Hello  world", "Xin chào")
    assert c.get("m", " Hello world ") == "Xin chào"


def test_models_do_not_mix():
    c = TranslationCache(10, None)
    c.put("a", "Hi", "A")
    assert c.get("b", "Hi") is None


def test_lru_eviction():
    c = TranslationCache(2, None)
    c.put("m", "1", "a")
    c.put("m", "2", "b")
    c.get("m", "1")  # 1 becomes most recent
    c.put("m", "3", "c")
    assert c.get("m", "2") is None and c.get("m", "1") == "a" and c.get("m", "3") == "c"


def test_persists_in_sqlite(tmp_path):
    db = tmp_path / "cache.sqlite"
    c = TranslationCache(10, db)
    c.put("m", "Good morning", "Chào buổi sáng")
    c.close()
    c2 = TranslationCache(10, db)
    assert c2.get("m", "Good morning") == "Chào buổi sáng"
    c2.close()


def test_pair_logger_disabled_creates_nothing(tmp_path):
    PairLogger(tmp_path / "translations.jsonl", enabled=False).log("Hi", "Chào", "m", None)
    assert not (tmp_path / "translations.jsonl").exists()


def test_pair_logger_writes_utf8_jsonl(tmp_path):
    p = tmp_path / "sub" / "translations.jsonl"
    log = PairLogger(p, enabled=True)
    log.log("Hi", "Chào bạn", "vinai-en2vi", "reverse1999")
    log.log("Bye", "Tạm biệt", "vinai-en2vi", None)
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert rows[0] == {"source": "Hi", "translation": "Chào bạn", "model": "vinai-en2vi", "game": "reverse1999"}
    assert rows[1]["translation"] == "Tạm biệt"
