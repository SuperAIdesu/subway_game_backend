"""Hardcoded sample data for the mock API.

Values are real rows copied from `gtfs_subway/`, kept tiny on purpose: this
module exists only so the endpoints return plausible responses until the
actual GTFS loading logic is implemented. Swap these dicts for real lookups
later; the models and endpoint signatures should not need to change.
"""

from .models import NextTrip, Route, Station, StopTime, Trip

# --- Stations (from stops.txt, parent stations) -------------------------------

STATIONS: dict[str, Station] = {
    "101": Station(
        id="101",
        name="Van Cortlandt Park-242 St",
        lat=40.889248,
        lon=-73.898583,
        on_lines=["1"],
    ),
    "103": Station(
        id="103",
        name="238 St",
        lat=40.884667,
        lon=-73.900870,
        on_lines=["1"],
    ),
    "104": Station(
        id="104",
        name="231 St",
        lat=40.878856,
        lon=-73.904834,
        on_lines=["1"],
    ),
    "106": Station(
        id="106",
        name="Marble Hill-225 St",
        lat=40.874561,
        lon=-73.909831,
        on_lines=["1"],
    ),
    "107": Station(
        id="107",
        name="215 St",
        lat=40.869444,
        lon=-73.915279,
        on_lines=["1"],
    ),
    "127": Station(
        id="127",
        name="Times Sq-42 St",
        lat=40.755290,
        lon=-73.987495,
        on_lines=["1", "2", "3", "7", "N", "Q", "R", "W", "GS"],
    ),
    "A31": Station(
        id="A31",
        name="High St",
        lat=40.698322,
        lon=-73.990241,
        on_lines=["A", "C"],
    ),
}

# --- Routes (from routes.txt) -------------------------------------------------

ROUTES: dict[str, Route] = {
    "1": Route(
        route_id="1",
        route_short_name="1",
        route_long_name="Broadway - 7 Avenue Local",
        route_type=1,
        route_desc="Trains operate between Van Cortlandt Park-242 St, Bronx and South Ferry, Manhattan at all times.",
        route_url="https://www.mta.info/schedules/subway/1-train",
        route_color="D82233",
        route_text_color="FFFFFF",
        route_sort_order=20,
    ),
    "A": Route(
        route_id="A",
        route_short_name="A",
        route_long_name="8 Avenue Express",
        route_type=1,
        route_desc=(
            "Trains operate between Inwood-207 St, Manhattan and Far Rockaway-Mott Av, Queens "
            "at all times. Also, from about 6 AM until about midnight, additional trains operate "
            "between Inwood-207 St and Ozone Park-Lefferts Blvd, Queens."
        ),
        route_url="https://www.mta.info/schedules/subway/a-train",
        route_color="0062CF",
        route_text_color="FFFFFF",
        route_sort_order=1,
    ),
    "C": Route(
        route_id="C",
        route_short_name="C",
        route_long_name="8 Avenue Local",
        route_type=1,
        route_desc="Trains operate between 168 St, Manhattan, and Euclid Av, Brooklyn, daily from about 6 AM to 11 PM.",
        route_url="https://www.mta.info/schedules/subway/c-train",
        route_color="0062CF",
        route_text_color="FFFFFF",
        route_sort_order=2,
    ),
}

# --- Stations on a route (from the route's trips in trips.txt/stop_times.txt) --

ROUTE_STATIONS: dict[str, list[str]] = {
    "1": ["101", "103", "104", "106", "107", "127"],
    "A": ["A31", "127"],
    "C": ["A31", "127"],
}

# --- Trips (from trips.txt) ---------------------------------------------------

TRIPS: dict[str, list[Trip]] = {
    "1": [
        Trip(
            route_id="1",
            trip_id="ASP26GEN-1038-Sunday-00_000600_1..S03R",
            service_id="Sunday",
            trip_headsign="South Ferry",
            direction_id=1,
            shape_id="1..S03R",
        ),
        Trip(
            route_id="1",
            trip_id="ASP26GEN-1038-Sunday-00_002600_1..S03R",
            service_id="Sunday",
            trip_headsign="South Ferry",
            direction_id=1,
            shape_id="1..S03R",
        ),
    ],
    "A": [
        Trip(
            route_id="A",
            trip_id="BSP26GEN-A055-Sunday-00_000950_A..S74R",
            service_id="Sunday",
            trip_headsign="Far Rockaway-Mott Av",
            direction_id=1,
            shape_id="A..S74R",
        ),
        Trip(
            route_id="A",
            trip_id="BSP26GEN-A055-Sunday-00_002950_A..S74R",
            service_id="Sunday",
            trip_headsign="Far Rockaway-Mott Av",
            direction_id=1,
            shape_id="A..S74R",
        ),
    ],
}

# --- Stop times (from stop_times.txt) ------------------------------------------

STOP_TIMES: dict[str, list[StopTime]] = {
    "ASP26GEN-1038-Sunday-00_000600_1..S03R": [
        StopTime(trip_id="ASP26GEN-1038-Sunday-00_000600_1..S03R", stop_id="101S", arrival_time="00:06:00", departure_time="00:06:00", stop_sequence=1),
        StopTime(trip_id="ASP26GEN-1038-Sunday-00_000600_1..S03R", stop_id="103S", arrival_time="00:07:30", departure_time="00:07:30", stop_sequence=2),
        StopTime(trip_id="ASP26GEN-1038-Sunday-00_000600_1..S03R", stop_id="104S", arrival_time="00:09:00", departure_time="00:09:00", stop_sequence=3),
        StopTime(trip_id="ASP26GEN-1038-Sunday-00_000600_1..S03R", stop_id="106S", arrival_time="00:10:30", departure_time="00:10:30", stop_sequence=4),
        StopTime(trip_id="ASP26GEN-1038-Sunday-00_000600_1..S03R", stop_id="107S", arrival_time="00:12:00", departure_time="00:12:00", stop_sequence=5),
    ],
    "BSP26GEN-A055-Sunday-00_000950_A..S74R": [
        StopTime(trip_id="BSP26GEN-A055-Sunday-00_000950_A..S74R", stop_id="A31S", arrival_time="00:09:50", departure_time="00:09:50", stop_sequence=1),
        StopTime(trip_id="BSP26GEN-A055-Sunday-00_000950_A..S74R", stop_id="127S", arrival_time="00:18:30", departure_time="00:18:30", stop_sequence=2),
    ],
}

# --- "Next trips" sample (station_id -> trips passing through, by time) ---------

NEXT_TRIPS: dict[str, list[NextTrip]] = {
    "101": [
        NextTrip(
            route_id="1",
            trip_id="ASP26GEN-1038-Sunday-00_000600_1..S03R",
            service_id="Sunday",
            trip_headsign="South Ferry",
            direction_id=1,
            shape_id="1..S03R",
            arrival_time="00:06:00",
            departure_time="00:06:00",
            stop_sequence=1,
        ),
        NextTrip(
            route_id="1",
            trip_id="ASP26GEN-1038-Sunday-00_002600_1..S03R",
            service_id="Sunday",
            trip_headsign="South Ferry",
            direction_id=1,
            shape_id="1..S03R",
            arrival_time="00:26:00",
            departure_time="00:26:00",
            stop_sequence=1,
        ),
    ],
    "A31": [
        NextTrip(
            route_id="A",
            trip_id="BSP26GEN-A055-Sunday-00_000950_A..S74R",
            service_id="Sunday",
            trip_headsign="Far Rockaway-Mott Av",
            direction_id=1,
            shape_id="A..S74R",
            arrival_time="00:09:50",
            departure_time="00:09:50",
            stop_sequence=1,
        ),
    ],
}