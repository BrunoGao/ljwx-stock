from __future__ import annotations

from threading import Lock

from app.strategy.base import BaseStrategy
from app.strategy.momentum_rule_v1 import MomentumRuleV1
from app.strategy.technical_pattern_v1 import TechnicalPatternV1

_STRATEGY_REGISTRY: dict[str, BaseStrategy] = {}
_STRATEGY_LOCK = Lock()


def register_strategy(strategy: BaseStrategy) -> None:
    with _STRATEGY_LOCK:
        if strategy.name in _STRATEGY_REGISTRY:
            raise ValueError(f"strategy '{strategy.name}' already registered")
        _STRATEGY_REGISTRY[strategy.name] = strategy


def list_strategies() -> list[BaseStrategy]:
    return list(_STRATEGY_REGISTRY.values())


def clear_strategies() -> None:
    with _STRATEGY_LOCK:
        _STRATEGY_REGISTRY.clear()


def register_builtin_strategies() -> None:
    with _STRATEGY_LOCK:
        if "momentum_rule_v1" not in _STRATEGY_REGISTRY:
            _STRATEGY_REGISTRY["momentum_rule_v1"] = MomentumRuleV1()
        if "technical_pattern_v1" not in _STRATEGY_REGISTRY:
            _STRATEGY_REGISTRY["technical_pattern_v1"] = TechnicalPatternV1()
