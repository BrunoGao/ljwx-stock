from datetime import date

from stock_etl.app.ingest import DateWindow, previous_quarter_window, to_date_str


def test_previous_quarter_window_q1() -> None:
    window = previous_quarter_window(date(2026, 2, 10))
    assert window == DateWindow(start=date(2025, 10, 1), end=date(2025, 12, 31))


def test_previous_quarter_window_q3() -> None:
    window = previous_quarter_window(date(2026, 8, 1))
    assert window == DateWindow(start=date(2026, 4, 1), end=date(2026, 6, 30))


def test_to_date_str() -> None:
    assert to_date_str(date(2026, 3, 4)) == "20260304"
