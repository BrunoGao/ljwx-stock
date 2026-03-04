from __future__ import annotations

import json
import logging

from pythonjsonlogger import jsonlogger

from stock_etl.app.config import get_settings
from stock_etl.app.db import connect_pg, ensure_market_tables
from stock_etl.app.ingest import run_ingest


def setup_logging(level: str) -> None:
    logger = logging.getLogger()
    logger.setLevel(level.upper())
    logger.handlers.clear()

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def main() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)

    logger = logging.getLogger("stock_etl")
    logger.info(
        "启动行情入库任务",
        extra={"run_mode": settings.run_mode, "adjust": settings.adjust},
    )

    try:
        conn = connect_pg(settings.database_url)
        try:
            ensure_market_tables(conn)
            summary = run_ingest(conn, settings)
        finally:
            conn.close()

        logger.info(
            "任务执行成功", extra={"summary": json.dumps(summary, ensure_ascii=False)}
        )
        return 0
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.error("任务执行失败", extra={"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
