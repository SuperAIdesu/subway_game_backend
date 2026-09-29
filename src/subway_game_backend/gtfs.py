"""Loading and indexing of the GTFS subway feed.

The feed is read from disk once (via pandas) and indexed into the structures
the API serves: parent stations with the routes serving them, ordered station
lists per route, trips per route, stop times per trip, and per-station
departures sorted by time. `load_data` caches the result, so the load cost is
paid once per process.
"""

import os
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Literal, NamedTuple

import pandas as pd

from .models import NextTrip, Route, Station, StopTime, Trip

#: Query-param pattern for GTFS local times (HH:MM:SS, hours may exceed 23).
GTFS_TIME_PATTERN = r"^\d{1,2}:\d{2}:\d{2}$"

#: Service-day types accepted by `get_next_trips`, mapped to calendar columns.
DayType = Literal["weekday", "saturday", "sunday"]


def parse_gtfs_time(value: str) -> int:
    """Convert a GTFS HH:MM:SS time to seconds since midnight.

    GTFS hours may exceed 23 (trips running past midnight), so this is a
    plain arithmetic conversion rather than a wall-clock time.
    """
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def gtfs_dir() -> Path:
    """Feed directory: `gtfs_subway/` in the repo root, or $GTFS_DATA_DIR."""
    override = os.environ.get("GTFS_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "gtfs_subway"


class Departure(NamedTuple):
    """One stop_time entry, indexed by the parent station it belongs to."""

    arrival_time: str
    departure_time: str
    arrival_sec: int
    departure_sec: int
    stop_sequence: int
    trip_id: str


class GtfsData:
    """In-memory indexes over a GTFS feed directory."""

    def __init__(self, directory: Path) -> None:
        stops_df = self._read_csv(directory / "stops.txt")
        routes_df = self._read_csv(directory / "routes.txt")
        trips_df = self._read_csv(directory / "trips.txt")
        stop_times_df = self._read_csv(directory / "stop_times.txt")

        self.routes: dict[str, Route] = self._build_routes(routes_df)

        # Children (platforms) point at their parent station; rows without a
        # parent are the stations themselves.
        parent_rows = stops_df[stops_df["parent_station"] == ""]
        self.child_to_parent: dict[str, str] = {
            row.stop_id: row.parent_station
            for row in stops_df.itertuples(index=False)
            if row.parent_station
        }

        trips_df["direction_id"] = pd.to_numeric(trips_df["direction_id"], errors="coerce")
        self.trips_by_id: dict[str, Trip] = {}
        self.trips_by_route: dict[str, list[Trip]] = defaultdict(list)
        for row in trips_df.itertuples(index=False):
            trip = Trip.model_construct(
                route_id=row.route_id,
                trip_id=row.trip_id,
                service_id=row.service_id,
                trip_headsign=row.trip_headsign or None,
                direction_id=None if pd.isna(row.direction_id) else int(row.direction_id),
                shape_id=row.shape_id or None,
            )
            self.trips_by_id[trip.trip_id] = trip
            self.trips_by_route[trip.route_id].append(trip)

        # Service-day index: each day type maps to the service_ids running on
        # it, from the weekly pattern in calendar.txt (supplemental services
        # like "Sunday-H-..." share the pattern of the day they serve).
        self.services_by_day: dict[str, set[str]] = {
            "weekday": set(),
            "saturday": set(),
            "sunday": set(),
        }
        calendar_path = directory / "calendar.txt"
        if calendar_path.exists():
            for row in self._read_csv(calendar_path).itertuples(index=False):
                if "1" in (row.monday, row.tuesday, row.wednesday, row.thursday, row.friday):
                    self.services_by_day["weekday"].add(row.service_id)
                if row.saturday == "1":
                    self.services_by_day["saturday"].add(row.service_id)
                if row.sunday == "1":
                    self.services_by_day["sunday"].add(row.service_id)

        stop_times_df["stop_sequence"] = pd.to_numeric(
            stop_times_df["stop_sequence"], errors="coerce"
        ).astype("Int64")
        stop_times_df["arrival_sec"] = stop_times_df["arrival_time"].map(parse_gtfs_time)
        stop_times_df["departure_sec"] = stop_times_df["departure_time"].map(parse_gtfs_time)
        stop_times_df["parent_id"] = stop_times_df["stop_id"].map(
            lambda stop_id: self.child_to_parent.get(stop_id, stop_id)
        )
        stop_times_df = stop_times_df.sort_values(
            ["trip_id", "stop_sequence"], kind="stable"
        ).reset_index(drop=True)

        self.stop_times_by_trip: dict[str, list[StopTime]] = {}
        for trip_id, group in stop_times_df.groupby("trip_id", sort=False):
            self.stop_times_by_trip[trip_id] = [
                StopTime.model_construct(
                    trip_id=trip_id,
                    stop_id=row.stop_id,
                    arrival_time=row.arrival_time,
                    departure_time=row.departure_time,
                    stop_sequence=int(row.stop_sequence),
                )
                for row in group.itertuples(index=False)
            ]

        # Departures indexed by parent station, sorted by arrival time.
        self.departures_by_station: dict[str, list[Departure]] = {}
        for station_id, group in stop_times_df.groupby("parent_id", sort=False):
            departures = [
                Departure(
                    arrival_time=row.arrival_time,
                    departure_time=row.departure_time,
                    arrival_sec=int(row.arrival_sec),
                    departure_sec=int(row.departure_sec),
                    stop_sequence=int(row.stop_sequence),
                    trip_id=row.trip_id,
                )
                for row in group.itertuples(index=False)
            ]
            departures.sort(key=lambda dep: (dep.arrival_sec, dep.trip_id))
            self.departures_by_station[station_id] = departures

        self.route_stations: dict[str, list[str]] = self._build_route_stations()

        lines_by_station: dict[str, set[str]] = defaultdict(set)
        for route_id, station_ids in self.route_stations.items():
            for station_id in station_ids:
                lines_by_station[station_id].add(route_id)
        self.stations: dict[str, Station] = {
            row.stop_id: Station.model_construct(
                id=row.stop_id,
                name=row.stop_name,
                lat=float(row.stop_lat),
                lon=float(row.stop_lon),
                on_lines=sorted(lines_by_station.get(row.stop_id, set())),
            )
            for row in parent_rows.itertuples(index=False)
        }

    @staticmethod
    def _read_csv(path: Path) -> pd.DataFrame:
        """Read a GTFS csv; every column as str, blank cells as empty strings."""
        return pd.read_csv(path, dtype=str, keep_default_na=False)

    @staticmethod
    def _build_routes(routes_df: pd.DataFrame) -> dict[str, Route]:
        routes_df["route_sort_order"] = pd.to_numeric(
            routes_df["route_sort_order"], errors="coerce"
        )
        routes: dict[str, Route] = {}
        for row in routes_df.itertuples(index=False):
            routes[row.route_id] = Route.model_construct(
                route_id=row.route_id,
                route_short_name=row.route_short_name,
                route_long_name=row.route_long_name,
                route_type=int(row.route_type),
                route_desc=row.route_desc or None,
                route_url=row.route_url or None,
                route_color=row.route_color or None,
                route_text_color=row.route_text_color or None,
                route_sort_order=None if pd.isna(row.route_sort_order) else int(row.route_sort_order),
            )
        return routes

    def _build_route_stations(self) -> dict[str, list[str]]:
        """Ordered parent-station list per route.

        Longest trips first define the backbone order; stations only visited
        by branch trips are appended at the end.
        """
        parents_by_trip: dict[str, list[str]] = {}
        for trip_id, stop_times in self.stop_times_by_trip.items():
            ordered: list[str] = []
            last: str | None = None
            for stop_time in stop_times:
                parent = self.child_to_parent.get(stop_time.stop_id, stop_time.stop_id)
                if parent != last:
                    ordered.append(parent)
                    last = parent
            parents_by_trip[trip_id] = ordered

        route_stations: dict[str, list[str]] = {}
        for route_id, trips in self.trips_by_route.items():
            ordered: list[str] = []
            seen: set[str] = set()
            backbone = sorted(
                trips, key=lambda trip: len(parents_by_trip.get(trip.trip_id, ())), reverse=True
            )
            for trip in backbone:
                for parent in parents_by_trip.get(trip.trip_id, ()):
                    if parent not in seen:
                        seen.add(parent)
                        ordered.append(parent)
            route_stations[route_id] = ordered
        return route_stations

    def next_trips(
        self, station_id: str, time: str, limit: int, day: str = "weekday"
    ) -> list[NextTrip]:
        """Trips arriving at the station at or after `time` on the given day."""
        departures = self.departures_by_station.get(station_id)
        if departures is None:
            raise KeyError(station_id)
        allowed_services = self.services_by_day.get(day, set())
        threshold = parse_gtfs_time(time)
        results: list[NextTrip] = []
        for departure in departures:
            if departure.arrival_sec < threshold:
                continue
            trip = self.trips_by_id[departure.trip_id]
            if trip.service_id not in allowed_services:
                continue
            results.append(
                NextTrip.model_construct(
                    **trip.model_dump(),
                    arrival_time=departure.arrival_time,
                    departure_time=departure.departure_time,
                    stop_sequence=departure.stop_sequence,
                )
            )
            if len(results) == limit:
                break
        return results


@lru_cache(maxsize=None)
def _load_data(directory: str) -> GtfsData:
    return GtfsData(Path(directory))


def load_data() -> GtfsData:
    """Load (once) and return the feed data for the configured directory."""
    return _load_data(str(gtfs_dir()))