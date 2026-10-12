import pytest
from fastapi.testclient import TestClient

from aapli import load_real
from aapli.db import connect


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AAPLI_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("AAPLI_INCLUDE_SIMULATED", raising=False)
    load_real.run()
    conn = connect()
    conn.execute("INSERT INTO readings VALUES ('2026-10-09','bhatsa',1,'simulated')")
    conn.commit()
    conn.close()
    from aapli.api import app
    return TestClient(app)


def test_real_totals_match_bmc(client):
    s = client.get("/api/summary").json()
    assert s["current"]["date"] == "2026-10-08"
    assert s["current"]["storage_ml"] == 1364045
    assert [p["year"] for p in s["previous_years"]] == [2025, 2024]
    assert s["previous_years"][0]["percent"] == 99.03


def test_simulated_hidden_by_default(client):
    assert client.get("/api/meta").json()["last_date"] == "2026-10-08"
    assert all(r["source"] == "bmc" for r in client.get("/api/lakes/bhatsa/readings").json())


def test_simulated_visible_with_dev_flag(client, monkeypatch):
    monkeypatch.setenv("AAPLI_INCLUDE_SIMULATED", "1")
    assert client.get("/api/meta").json()["last_date"] == "2026-10-09"
