"""Fixtures for tests that need the recorder (it must start before hass)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from tests.ha.conftest import entry  # noqa: F401


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Any, enable_custom_integrations: None
) -> Generator[None]:
    """Recorder first, then allow custom_components."""
    yield
