from __future__ import annotations

from decimal import Decimal

from app.strategy.base import BaseStrategy, StrategyFeature, StrategySignal


class TechnicalPatternV1(BaseStrategy):
    name = "technical_pattern_v1"

    def score(self, features: list[StrategyFeature]) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        for feature in features:
            score = (
                feature.breakout_20d * Decimal("80")
                + feature.ret_5d * Decimal("40")
                - feature.vol_20d * Decimal("10")
            )
            confidence = feature.breakout_20d
            signals.append(
                StrategySignal(
                    symbol=feature.symbol,
                    trade_date=feature.trade_date,
                    strategy_name=self.name,
                    score=score,
                    confidence=confidence,
                    reason_json={
                        "breakout_20d": float(feature.breakout_20d),
                        "ret_5d": float(feature.ret_5d),
                    },
                )
            )
        return signals
