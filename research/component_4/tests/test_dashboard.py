"""Every dashboard page must render without an exception.  python -m pytest -q tests/test_dashboard.py"""
from pathlib import Path

import pytest

from src.config import PROCESSED

VIEWS = Path(__file__).resolve().parents[1] / "dashboard" / "views"

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(),
                                reason="run python -m src.data.build_dataset first")


@pytest.mark.parametrize("page", sorted(p.name for p in VIEWS.glob("*.py")))
def test_page_renders(page):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(VIEWS / page), default_timeout=300).run()   # slow CPU while training runs
    assert not at.exception, [e.message for e in at.exception]


def test_app_navigation_loads():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(VIEWS.parent / "app.py"), default_timeout=300).run()
    assert not at.exception, [e.message for e in at.exception]


def test_booking_from_the_page(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.control import booking
    monkeypatch.setattr(booking, "DB", tmp_path / "b.sqlite")          # never touch the demo bookings
    at = AppTest.from_file(str(VIEWS / "book.py"), default_timeout=300).run()
    at.button[0].click().run()                                         # "Book N place(s) ..."
    assert not at.exception, [e.message for e in at.exception]
    assert any("Your code" in s.value for s in at.success)
    assert len(booking.bookings_for(at.session_state["book_day"].isoformat())) == 1
