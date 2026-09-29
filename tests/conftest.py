"""Shared pytest fixtures."""

import pytest

from subway_game_backend.gtfs import GtfsData, load_data


@pytest.fixture(scope="session")
def data() -> GtfsData:
    """The real GTFS feed, loaded once for the whole test session."""
    return load_data()
