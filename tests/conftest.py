"""Shared fixtures for chainwind tests."""

from __future__ import annotations

from typing import Iterator, List

import pytest
from loguru import logger as _loguru_logger


@pytest.fixture
def loguru_capture() -> Iterator[List[str]]:
    """Capture loguru records as plain strings (caplog only sees stdlib logs)."""
    records: List[str] = []
    sink_id = _loguru_logger.add(lambda msg: records.append(str(msg)), level="TRACE")
    try:
        yield records
    finally:
        _loguru_logger.remove(sink_id)
