"""NYC subway GTFS API backend."""

import uvicorn

from .main import app


def main() -> None:
    """Run the API locally (entry point: `subway-game-backend`)."""
    uvicorn.run(app, host="127.0.0.1", port=8000)