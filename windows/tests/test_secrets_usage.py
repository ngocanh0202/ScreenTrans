"""DPAPI key store and the daily character counter."""
from datetime import date

from app.secrets import KeyStore
from app.usage import Usage


def test_keys_round_trip_encrypted_and_stripped(tmp_path):
    ks = KeyStore(tmp_path)
    assert ks.get("gemini") == ""
    ks.set("gemini", "  AIza-SECRET-1\n")
    ks.set("claude", "sk-ant-2")
    assert KeyStore(tmp_path).get("gemini") == "AIza-SECRET-1"
    raw = (tmp_path / "keys.bin").read_bytes()
    assert b"AIza-SECRET-1" not in raw and b"sk-ant-2" not in raw
    ks.set("gemini", "  ")  # empty removes
    assert KeyStore(tmp_path).get("gemini") == "" and KeyStore(tmp_path).get("claude") == "sk-ant-2"


def test_a_corrupt_key_file_reads_as_no_keys(tmp_path):
    (tmp_path / "keys.bin").write_bytes(b"\x00garbage")
    assert KeyStore(tmp_path).get("openai") == ""
    KeyStore(tmp_path).set("openai", "sk-o")  # and can be written again
    assert KeyStore(tmp_path).get("openai") == "sk-o"


def test_usage_counts_per_day_and_limits(tmp_path):  # RF4
    today = [date(2026, 11, 19)]
    u = Usage(tmp_path, clock=lambda: today[0])
    assert u.used() == 0 and u.allows(100, 150)
    u.add(100)
    assert Usage(tmp_path, clock=lambda: today[0]).used() == 100
    assert not u.allows(51, 150) and u.allows(50, 150)
    today[0] = date(2026, 11, 20)  # local midnight passed
    assert u.used() == 0 and u.allows(150, 150)


def test_a_broken_usage_file_starts_from_zero(tmp_path):
    (tmp_path / "usage.json").write_text("{nope", encoding="utf-8")
    assert Usage(tmp_path).used() == 0
