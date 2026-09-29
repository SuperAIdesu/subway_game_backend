"""Endpoint tests against the real feed via the FastAPI test client."""

from fastapi.testclient import TestClient

from subway_game_backend.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "spec": "/docs"}


def test_all_stations(data) -> None:
    response = client.get("/all_stations")
    assert response.status_code == 200
    ids = response.json()
    assert all(isinstance(station_id, str) for station_id in ids)
    assert len(ids) == len(set(ids))
    assert set(ids) == set(data.stations)
    assert "101" in ids


def test_all_stations_entries_are_queryable() -> None:
    """Every listed station id must be retrievable via /get_station."""
    for station_id in client.get("/all_stations").json():
        assert client.get("/get_station", params={"station_id": station_id}).status_code == 200


def test_all_routes(data) -> None:
    response = client.get("/all_routes")
    assert response.status_code == 200
    route_ids = response.json()
    assert all(isinstance(route_id, str) for route_id in route_ids)
    assert len(route_ids) == len(set(route_ids))
    assert set(route_ids) == set(data.routes)
    # Canonical MTA order: A/C/E first, Staten Island Railway last.
    assert route_ids[:3] == ["A", "C", "E"]
    assert route_ids[-1] == "SI"


def test_all_routes_entries_are_queryable() -> None:
    """Every listed route id must be retrievable via /get_route."""
    for route_id in client.get("/all_routes").json():
        assert client.get("/get_route", params={"route_id": route_id}).status_code == 200


def test_get_station() -> None:
    response = client.get("/get_station", params={"station_id": "101"})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "101"
    assert body["name"] == "Van Cortlandt Park-242 St"
    assert body["lat"] == 40.889248
    assert body["lon"] == -73.898583
    assert body["on_lines"] == ["1"]


def test_get_station_unknown_id() -> None:
    response = client.get("/get_station", params={"station_id": "NOPE"})
    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


def test_get_route() -> None:
    response = client.get("/get_route", params={"route_id": "A"})
    assert response.status_code == 200
    body = response.json()
    assert body["route_id"] == "A"
    assert body["route_short_name"] == "A"
    assert body["route_long_name"] == "8 Avenue Express"
    assert body["route_type"] == 1
    assert body["route_color"] == "0062CF"
    assert body["route_url"].startswith("https://www.mta.info/")


def test_get_route_unknown_id() -> None:
    response = client.get("/get_route", params={"route_id": "ZZ"})
    assert response.status_code == 404


def test_get_route_stations() -> None:
    response = client.get("/get_route_stations", params={"route_id": "1"})
    assert response.status_code == 200
    stations = response.json()
    assert len(stations) > 30
    ids = [station["id"] for station in stations]
    assert len(ids) == len(set(ids))
    assert "101" in ids
    assert all("1" in station["on_lines"] for station in stations)


def test_get_route_stations_unknown_id() -> None:
    response = client.get("/get_route_stations", params={"route_id": "ZZ"})
    assert response.status_code == 404


def test_get_trips() -> None:
    response = client.get("/get_trips", params={"route_id": "1"})
    assert response.status_code == 200
    trips = response.json()
    assert len(trips) > 100
    assert all(trip["route_id"] == "1" for trip in trips)
    first = trips[0]
    assert first["trip_id"]
    assert first["service_id"]
    assert first["direction_id"] in (0, 1, None)


def test_get_trips_unknown_id() -> None:
    response = client.get("/get_trips", params={"route_id": "ZZ"})
    assert response.status_code == 404


def test_get_trip_stoptimes() -> None:
    trip_id = client.get("/get_trips", params={"route_id": "1"}).json()[0]["trip_id"]
    response = client.get("/get_trip_stoptimes", params={"trip_id": trip_id})
    assert response.status_code == 200
    stop_times = response.json()
    assert stop_times
    sequences = [st["stop_sequence"] for st in stop_times]
    assert sequences == sorted(sequences)
    assert all(st["trip_id"] == trip_id for st in stop_times)
    assert all(len(st["arrival_time"]) == 8 for st in stop_times)


def test_get_trip_stoptimes_unknown_id() -> None:
    response = client.get("/get_trip_stoptimes", params={"trip_id": "NOPE"})
    assert response.status_code == 404


def test_get_next_trips_matches_trip_stoptimes(data) -> None:
    """A trip's first stop must show up in that station's next-trips list."""
    trip_id = "ASP26GEN-1038-Sunday-00_000600_1..S03R"
    stoptimes = client.get("/get_trip_stoptimes", params={"trip_id": trip_id}).json()
    first_stop = stoptimes[0]
    station_id = data.child_to_parent.get(first_stop["stop_id"], first_stop["stop_id"])

    response = client.get(
        "/get_next_trips",
        params={"station_id": station_id, "time": "00:00:00", "day": "sunday", "limit": 100},
    )
    assert response.status_code == 200
    next_trips = response.json()
    arrivals = {trip["trip_id"]: trip["arrival_time"] for trip in next_trips}
    assert arrivals[trip_id] == first_stop["arrival_time"]


def test_get_next_trips_respects_time_and_limit() -> None:
    response = client.get(
        "/get_next_trips", params={"station_id": "127", "time": "12:00:00", "limit": 5}
    )
    assert response.status_code == 200
    next_trips = response.json()
    assert 0 < len(next_trips) <= 5
    arrivals = [trip["arrival_time"] for trip in next_trips]
    assert arrivals == sorted(arrivals)
    assert all(arrival >= "12:00:00" for arrival in arrivals)


def test_get_next_trips_default_limit() -> None:
    response = client.get(
        "/get_next_trips", params={"station_id": "127", "time": "12:00:00"}
    )
    assert response.status_code == 200
    assert len(response.json()) <= 20


def test_get_next_trips_unknown_station() -> None:
    response = client.get(
        "/get_next_trips", params={"station_id": "NOPE", "time": "12:00:00"}
    )
    assert response.status_code == 404


def test_get_next_trips_day_filter(data) -> None:
    """Only trips on the requested day's service calendars may be returned."""
    for day in ("weekday", "saturday", "sunday"):
        response = client.get(
            "/get_next_trips", params={"station_id": "101", "time": "12:00:00", "day": day, "limit": 10}
        )
        assert response.status_code == 200
        trips = response.json()
        assert trips, day
        assert all(trip["service_id"] in data.services_by_day[day] for trip in trips)


def test_get_next_trips_defaults_to_weekday(data) -> None:
    response = client.get("/get_next_trips", params={"station_id": "101", "time": "12:00:00"})
    assert response.status_code == 200
    trips = response.json()
    assert trips
    assert all(trip["service_id"] in data.services_by_day["weekday"] for trip in trips)


def test_get_next_trips_unknown_day() -> None:
    response = client.get(
        "/get_next_trips", params={"station_id": "101", "time": "12:00:00", "day": "funday"}
    )
    assert response.status_code == 422


def test_get_next_trips_invalid_time() -> None:
    for bad_time in ("12:00", "not-a-time", "ab:cd:ef"):
        response = client.get(
            "/get_next_trips", params={"station_id": "101", "time": bad_time}
        )
        assert response.status_code == 422, bad_time
