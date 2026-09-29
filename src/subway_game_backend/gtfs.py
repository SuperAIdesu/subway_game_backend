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

#: Snap distance (degrees, ~11m) below which a merged-shape point is treated
#: as already covered by the polyline built so far.
MERGE_SNAP = 0.0001


def _perpendicular_distance(point: list[float], start: list[float], end: list[float]) -> float:
    """Distance (degrees) from `point` to the segment start->end."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
    scale = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    scale = min(1.0, max(0.0, scale))  # clamp to the segment
    proj_x, proj_y = start[0] + scale * dx, start[1] + scale * dy
    return ((point[0] - proj_x) ** 2 + (point[1] - proj_y) ** 2) ** 0.5


def _simplify_polyline(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """Douglas-Peucker simplification of a [lon, lat] polyline."""
    if len(points) < 3:
        return list(points)

    def recurse(chunk: list[list[float]]) -> list[list[float]]:
        if len(chunk) < 3:
            return chunk
        start, end = chunk[0], chunk[-1]
        index, max_dist = 0, 0.0
        for i in range(1, len(chunk) - 1):
            dist = _perpendicular_distance(chunk[i], start, end)
            if dist > max_dist:
                index, max_dist = i, dist
        if max_dist <= tolerance:
            return [start, end]
        left = recurse(chunk[: index + 1])
        return left[:-1] + recurse(chunk[index:])

    return recurse(points)


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
        shapes_df = self._read_csv(directory / "shapes.txt")

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

        # Shape index: shape_id -> ordered [lon, lat] points, plus the route
        # and direction each shape belongs to (a shape is used by exactly one
        # route in this feed).
        shapes_df["shape_pt_sequence"] = pd.to_numeric(
            shapes_df["shape_pt_sequence"], errors="coerce"
        )
        self.shapes_by_id: dict[str, list[list[float]]] = {}
        for shape_id, group in shapes_df.groupby("shape_id", sort=False):
            ordered = group.sort_values("shape_pt_sequence", kind="stable")
            self.shapes_by_id[shape_id] = [
                [float(lon), float(lat)]
                for lon, lat in zip(ordered["shape_pt_lon"], ordered["shape_pt_lat"], strict=True)
            ]
        self.route_by_shape: dict[str, str] = {}
        self.direction_by_shape: dict[str, int | None] = {}
        for row in trips_df.itertuples(index=False):
            if row.shape_id and row.shape_id not in self.route_by_shape:
                self.route_by_shape[row.shape_id] = row.route_id
                self.direction_by_shape[row.shape_id] = (
                    None if pd.isna(row.direction_id) else int(row.direction_id)
                )

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

    def route_shape(
        self,
        route_id: str,
        direction_id: int | None = None,
        simplify_tolerance: float | None = None,
    ) -> list[list[float]]:
        """Polyline ([lon, lat] pairs) covering a route's track.

        With `direction_id` set, only shapes of that direction are used.
        Otherwise all of the route's shapes are merged into one polyline.

        `simplify_tolerance` (degrees, e.g. 0.0005) applies Douglas-Peucker
        simplification to reduce the point count for map rendering.
        """
        shape_ids = [
            shape_id
            for shape_id in self.shapes_by_id
            if self.route_by_shape.get(shape_id) == route_id
            and (direction_id is None or self.direction_by_shape.get(shape_id) == direction_id)
        ]
        if not shape_ids:
            return []
        coordinates = (
            self.shapes_by_id[max(shape_ids, key=lambda s: len(self.shapes_by_id[s]))]
            if direction_id is not None
            else self._merge_shapes(shape_ids)
        )
        if simplify_tolerance:
            coordinates = _simplify_polyline(coordinates, simplify_tolerance)
        return coordinates

    def _merge_shapes(self, shape_ids: list[str]) -> list[list[float]]:
        """Union several shape polylines into one continuous track.

        The longest shape is the backbone. Other shapes share the trunk and
        diverge near their ends (branch terminals, loops): for each, the
        divergent tail (points after its last on-backbone point) is spliced
        in at the backbone position where the shape left it, keeping the
        result a single walkable polyline.
        """
        ordered = sorted(shape_ids, key=lambda s: len(self.shapes_by_id[s]), reverse=True)
        backbone: list[list[float]] = list(self.shapes_by_id[ordered[0]])
        for shape_id in ordered[1:]:
            points = self.shapes_by_id[shape_id]
            last_on_backbone = self._last_contained_index(backbone, points)
            if last_on_backbone is None:
                continue  # fully contained or unrelated; nothing new to add
            tail = points[last_on_backbone + 1 :]
            if not tail:
                continue
            # Splice the tail right after the backbone point the shape left from.
            anchor = self._closest_index(backbone, points[last_on_backbone])
            backbone[anchor + 1 : anchor + 1] = [list(p) for p in tail]
        return backbone

    @staticmethod
    def _last_contained_index(
        backbone: list[list[float]], points: list[list[float]], tol: float = 2e-4
    ) -> int | None:
        """Index of the last point of `points` that lies on the backbone."""
        grid = {(round(p[0], 5), round(p[1], 5)) for p in backbone}
        for i in range(len(points) - 1, -1, -1):
            lon, lat = points[i]
            if (round(lon, 5), round(lat, 5)) in grid:
                return i
        return None

    @staticmethod
    def _closest_index(
        backbone: list[list[float]], point: list[float]
    ) -> int:
        return min(
            range(len(backbone)),
            key=lambda i: (backbone[i][0] - point[0]) ** 2 + (backbone[i][1] - point[1]) ** 2,
        )

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
        self, station_id: str, time: str, limit: int | None = None, day: str = "weekday"
    ) -> list[NextTrip]:
        """Trips arriving at the station at or after `time` on the given day.

        With `limit=None` (the default), every remaining trip of the day is returned.
        """
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
            if limit is not None and len(results) == limit:
                break
        return results


@lru_cache(maxsize=None)
def _load_data(directory: str) -> GtfsData:
    return GtfsData(Path(directory))


def load_data() -> GtfsData:
    """Load (once) and return the feed data for the configured directory."""
    return _load_data(str(gtfs_dir()))