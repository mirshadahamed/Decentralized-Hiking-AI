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
    at = AppTest.from_file(str(VIEWS / page), default_timeout=120).run()
    assert not at.exception, [e.message for e in at.exception]
