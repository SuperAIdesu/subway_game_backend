"""Unit tests for the GTFS loader and its indexes."""

import pytest

from subway_game_backend.gtfs import parse_gtfs_time


def test_stations_loaded(data) -> None:
    station = data.stations["101"]
    assert station.name == "Van Cortlandt Park-242 St"
    assert station.lat == pytest.approx(40.889248)
    assert station.lon == pytest.approx(-73.898583)
    assert "1" in station.on_lines  # northern terminus of the 1
    assert station.on_lines == sorted(station.on_lines)


def test_interchange_station_lists_multiple_lines(data) -> None:
    # Times Sq-42 St is served by the 1/2/3; the 7/N/Q/R/W platforms live
    # under separate parent stations in this feed (see transfers.txt).
    on_lines = data.stations["127"].on_lines
    assert "1" in on_lines
    assert len(on_lines) >= 2


def test_all_parent_stations_loaded(data) -> None:
    # stops.txt has 1488 rows: parent stations plus platforms/children.
    assert len(data.stations) > 100
    # A stop id is either a station (no parent) or a platform (has one), never both.
    assert not set(data.stations) & set(data.child_to_parent)


def test_routes_loaded(data) -> None:
    route = data.routes["A"]
    assert route.route_short_name == "A"
    assert route.route_long_name == "8 Avenue Express"
    assert route.route_type == 1
    assert route.route_color == "0062CF"
    assert route.route_text_color == "FFFFFF"
    assert route.route_sort_order == 1


def test_route_stations_are_ordered_and_unique(data) -> None:
    station_ids = data.route_stations["1"]
    assert len(station_ids) > 30  # the 1 has 38 stations in this feed
    assert "101" in station_ids  # Van Cortlandt Park-242 St
    assert "127" in station_ids  # Times Sq-42 St
    assert len(station_ids) == len(set(station_ids))


def test_route_stations_reference_known_stations(data) -> None:
    for route_id, station_ids in data.route_stations.items():
        assert set(station_ids) <= set(data.stations), route_id
        for station_id in station_ids:
            assert route_id in data.stations[station_id].on_lines


def test_trips_grouped_by_route(data) -> None:
    trips = data.trips_by_route["1"]
    assert len(trips) > 100
    assert all(trip.route_id == "1" for trip in trips)
    assert all(data.trips_by_id[trip.trip_id] is trip for trip in trips)


def test_trip_direction_ids_are_zero_one_or_none(data) -> None:
    direction_ids = {trip.direction_id for trip in data.trips_by_route["1"]}
    assert direction_ids <= {0, 1, None}


def test_stop_times_sorted_by_sequence(data) -> None:
    for trip_id in list(data.stop_times_by_trip)[:100]:
        sequences = [st.stop_sequence for st in data.stop_times_by_trip[trip_id]]
        assert sequences == sorted(sequences), trip_id


def test_stop_time_fields(data) -> None:
    stop_times = data.stop_times_by_trip["ASP26GEN-1038-Sunday-00_000600_1..S03R"]
    assert stop_times[0].stop_id == "101S"
    assert stop_times[0].arrival_time == "00:06:00"
    assert stop_times[0].departure_time == "00:06:00"
    assert stop_times[0].stop_sequence == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00:06:00", 360),
        ("01:00:00", 3600),
        ("25:30:00", 91_800),  # GTFS allows hours past midnight
    ],
)
def test_parse_gtfs_time(value: str, expected: int) -> None:
    assert parse_gtfs_time(value) == expected


def test_departures_sorted_by_time(data) -> None:
    departures = data.departures_by_station["101"]
    assert len(departures) > 1
    seconds = [dep.arrival_sec for dep in departures]
    assert seconds == sorted(seconds)


def test_next_trips_returns_soonest_first(data) -> None:
    trips = data.next_trips("101", "00:00:00", limit=10)
    assert 0 < len(trips) <= 10
    arrivals = [trip.arrival_time for trip in trips]
    assert arrivals == sorted(arrivals)


def test_next_trips_respects_time_threshold(data) -> None:
    trips = data.next_trips("101", "00:06:00", limit=5)
    assert trips
    assert all(trip.arrival_time >= "00:06:00" for trip in trips)


def test_next_trips_unknown_station(data) -> None:
    with pytest.raises(KeyError):
        data.next_trips("NOPE", "00:00:00", limit=5)


def test_next_trips_without_limit_returns_all(data) -> None:
    """With limit=None, every remaining trip of the day is returned."""
    trips = data.next_trips("101", "00:00:00", limit=None, day="sunday")
    allowed = data.services_by_day["sunday"]
    expected = [
        departure
        for departure in data.departures_by_station["101"]
        if data.trips_by_id[departure.trip_id].service_id in allowed
    ]
    assert len(trips) == len(expected) > 20


def test_services_by_day(data) -> None:
    assert "Weekday" in data.services_by_day["weekday"]
    assert "Saturday" in data.services_by_day["saturday"]
    assert "Sunday" in data.services_by_day["sunday"]
    # Dated supplement calendars belong to the day they serve.
    assert any(s.startswith("Sunday-H-") for s in data.services_by_day["sunday"])
    assert "Sunday" not in data.services_by_day["weekday"]


def test_next_trips_filtered_by_day(data) -> None:
    for day in ("weekday", "saturday", "sunday"):
        trips = data.next_trips("101", "12:00:00", limit=5, day=day)
        assert trips, day
        assert all(trip.service_id in data.services_by_day[day] for trip in trips)


def test_load_data_is_cached() -> None:
    from subway_game_backend import gtfs

    assert gtfs.load_data() is gtfs.load_data()
