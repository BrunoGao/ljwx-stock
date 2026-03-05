from __future__ import annotations

from decimal import Decimal

from app.strategy.base import BaseStrategy, StrategyFeature, StrategySignal


class MomentumRuleV1(BaseStrategy):
    name = "momentum_rule_v1"

    def score(self, features: list[StrategyFeature]) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        for feature in features:
            score = feature.ret_5d * Decimal("100") - feature.vol_20d * Decimal("20")
            confidence = Decimal("1") / (Decimal("1") + feature.vol_20d)
            signals.append(
                StrategySignal(
                    symbol=feature.symbol,
                    trade_date=feature.trade_date,
                    strategy_name=self.name,
                    score=score,
                    confidence=confidence,
                    reason_json={
                        "ret_5d": float(feature.ret_5d),
                        "vol_20d": float(feature.vol_20d),
                    },
                )
            )
        return signals
