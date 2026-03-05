from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrategyFeature(BaseModel):
    symbol: str
    trade_date: date
    ret_5d: Decimal
    vol_20d: Decimal
    amount_avg_20d: Decimal
    breakout_20d: Decimal

    model_config = ConfigDict(frozen=True)


class StrategySignal(BaseModel):
    symbol: str
    trade_date: date
    strategy_name: str
    score: Decimal
    confidence: Decimal
    reason_json: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class StrategyReco(BaseModel):
    symbol: str
    trade_date: date
    strategy_name: str
    score: Decimal
    confidence: Decimal
    rank: int
    reason_json: dict[str, object] = Field(default_factory=dict)
    model_version: str
    data_cutoff: date
    code_version: str
    params_hash: str

    model_config = ConfigDict(frozen=True)


class BaseStrategy(ABC):
    name: str

    @abstractmethod
    def score(self, features: list[StrategyFeature]) -> list[StrategySignal]:
        raise NotImplementedError
