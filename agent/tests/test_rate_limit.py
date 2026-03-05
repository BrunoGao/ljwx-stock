# ruff: noqa: E402

from pathlib import Path
import sys

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rate_limit import RateLimiter


def test_rate_limit_31st_request_returns_429() -> None:
    app = FastAPI()
    limiter = RateLimiter(rpm=30)

    @app.get("/limited")
    async def limited(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> dict[str, bool]:
        if x_api_key != "test-key":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效"
            )

        allowed = await limiter.allow_request(x_api_key)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded，超过每分钟请求上限",
            )
        return {"ok": True}

    client = TestClient(app)

    for _ in range(30):
        response = client.get("/limited", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200

    blocked_response = client.get("/limited", headers={"X-API-Key": "test-key"})
    assert blocked_response.status_code == 429
    assert "rate limit" in blocked_response.text
