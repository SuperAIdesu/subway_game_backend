"""Pydantic data models for the subway GTFS API.

Field names follow the GTFS spec (snake_case), matching the `gtfs_subway/`
feed files.
"""

from pydantic import BaseModel, Field


class Station(BaseModel):
    """A subway station (GTFS `stops.txt`, parent stations only)."""

    id: str = Field(description="GTFS stop_id of the parent station")
    name: str = Field(description="Station name")
    lat: float = Field(description="Latitude")
    lon: float = Field(description="Longitude")
    on_lines: list[str] = Field(
        description="Route ids serving this station, e.g. ['1', '2', '3']",
    )


class Route(BaseModel):
    """A subway line (GTFS `routes.txt`)."""

    route_id: str
    route_short_name: str
    route_long_name: str
    route_type: int = Field(description="GTFS route type; 1 = subway")
    route_desc: str | None = None
    route_url: str | None = None
    route_color: str | None = None
    route_text_color: str | None = None
    route_sort_order: int | None = None


class Trip(BaseModel):
    """A single scheduled train run (GTFS `trips.txt`)."""

    route_id: str
    trip_id: str
    service_id: str
    trip_headsign: str | None = None
    direction_id: int | None = Field(default=None, description="0 = uptown, 1 = downtown")
    shape_id: str | None = None


class StopTime(BaseModel):
    """One stop on a trip's schedule (GTFS `stop_times.txt`).

    Times are HH:MM:SS strings as in the GTFS feed (can exceed 24:00:00).
    """

    trip_id: str
    stop_id: str
    arrival_time: str
    departure_time: str
    stop_sequence: int


class NextTrip(Trip):
    """A trip passing through a station, with the time it will be there.

    Extends the draft spec's "list of trips" with the scheduled times at the
    requested station, which is what a "next trips" consumer usually needs.
    """

    arrival_time: str
    departure_time: str
    stop_sequence: int