import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class BucketState:
    tokens: float
    last_refill_ts: float


class RateLimiter:
    def __init__(self, rpm: int) -> None:
        if rpm <= 0:
            raise ValueError("rate limit rpm must be positive")
        self._capacity: float = float(rpm)
        self._tokens_per_second: float = float(rpm) / 60.0
        self._buckets: dict[str, BucketState] = {}
        self._lock = asyncio.Lock()

    async def allow_request(self, api_key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            state = self._buckets.get(api_key)
            if state is None:
                state = BucketState(tokens=self._capacity, last_refill_ts=now)
                self._buckets[api_key] = state

            elapsed = now - state.last_refill_ts
            refill_tokens = elapsed * self._tokens_per_second
            state.tokens = min(self._capacity, state.tokens + refill_tokens)
            state.last_refill_ts = now

            if state.tokens >= 1.0:
                state.tokens -= 1.0
                return True
            return False
