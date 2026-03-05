# ruff: noqa: E402

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import db
from app.strategy.base import StrategyReco


class _FakeConn:
    def __init__(self) -> None:
        self.query: str = ""
        self.values: list[tuple[object, ...]] = []

    async def executemany(
        self, query: str, values: list[tuple[object, ...]], timeout: float
    ) -> None:
        self.query = query
        self.values = values
        assert timeout > 0


class _FakeAcquire:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._conn)


def test_reco_write_upsert_and_fields(monkeypatch) -> None:
    fake_conn = _FakeConn()
    fake_pool = _FakePool(fake_conn)

    monkeypatch.setattr(db, "_get_pool", lambda: fake_pool)

    row = StrategyReco(
        symbol="600519",
        trade_date=date(2024, 3, 1),
        strategy_name="strategy_ensemble_v1",
        score=Decimal("1.23"),
        confidence=Decimal("0.88"),
        rank=1,
        reason_json={"filtered": False, "threshold": "10000000"},
        model_version="strategy_ensemble_v1@v1",
        data_cutoff=date(2024, 3, 1),
        code_version="unknown",
        params_hash="abcd1234abcd1234",
    )

    inserted = asyncio.run(db.insert_reco_daily_rows([row]))

    assert inserted == 1
    assert (
        "ON CONFLICT (symbol, trade_date, strategy_name) DO UPDATE SET"
        in fake_conn.query
    )
    assert "score = EXCLUDED.score" in fake_conn.query
    assert "confidence = EXCLUDED.confidence" in fake_conn.query
    assert "rank = EXCLUDED.rank" in fake_conn.query
    assert "reason_json = EXCLUDED.reason_json" in fake_conn.query
    assert "model_version = EXCLUDED.model_version" in fake_conn.query
    assert "data_cutoff = EXCLUDED.data_cutoff" in fake_conn.query
    assert "code_version = EXCLUDED.code_version" in fake_conn.query
    assert "params_hash = EXCLUDED.params_hash" in fake_conn.query
    assert "created_at = EXCLUDED.created_at" not in fake_conn.query

    payload = fake_conn.values[0]
    assert payload[8] == date(2024, 3, 1)
    assert payload[9] == "unknown"
    assert payload[10] == "abcd1234abcd1234"
    parsed_reason = json.loads(str(payload[6]))
    assert parsed_reason["filtered"] is False
