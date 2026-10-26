"""Isolate process-global in-memory state between tests."""

import pytest

from app.cache.store import cache, store


@pytest.fixture(autouse=True)
def reset_search_state():
    cache.clear()
    store.clear()
    yield
    cache.clear()
    store.clear()
