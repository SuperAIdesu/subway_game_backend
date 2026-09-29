"""FastAPI application exposing NYC subway GTFS data.

Endpoints serve the feed in `gtfs_subway/` (or `$GTFS_DATA_DIR`), loaded into
memory by `gtfs.load_data()` on first use.
"""

from fastapi import FastAPI, HTTPException, Query

from . import gtfs
from .models import NextTrip, Route, Station, StopTime, Trip

app = FastAPI(
    title="NYC Subway GTFS API",
    description="API over MTA subway GTFS data: lines, stations, trips, stop times.",
    version="0.2.0",
)


@app.get("/", operation_id="health")
def root() -> dict[str, str]:
    return {"status": "ok", "spec": "/docs"}


@app.get("/get_station", response_model=Station, operation_id="get_station")
def get_station(
    station_id: str = Query(description="GTFS stop_id of a parent station, e.g. 101"),
) -> Station:
    """Get a single station, including the lines it is on."""
    data = gtfs.load_data()
    station = data.stations.get(station_id)
    if station is None:
        raise HTTPException(status_code=404, detail=f"Unknown station id: {station_id}")
    return station


@app.get("/get_route", response_model=Route, operation_id="get_route")
def get_route(
    route_id: str = Query(description="GTFS route_id, e.g. 1 or A"),
) -> Route:
    """Get a single line (route)."""
    data = gtfs.load_data()
    route = data.routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Unknown route id: {route_id}")
    return route


@app.get("/get_route_stations", response_model=list[Station], operation_id="get_route_stations")
def get_route_stations(
    route_id: str = Query(description="GTFS route_id, e.g. 1 or A"),
) -> list[Station]:
    """Get the ordered list of stations that a line contains."""
    data = gtfs.load_data()
    station_ids = data.route_stations.get(route_id)
    if station_ids is None:
        raise HTTPException(status_code=404, detail=f"Unknown route id: {route_id}")
    return [data.stations[station_id] for station_id in station_ids]


@app.get("/get_trips", response_model=list[Trip], operation_id="get_trips")
def get_trips(
    route_id: str = Query(description="GTFS route_id, e.g. 1 or A"),
) -> list[Trip]:
    """Get the list of trips for a line."""
    data = gtfs.load_data()
    if route_id not in data.routes:
        raise HTTPException(status_code=404, detail=f"Unknown route id: {route_id}")
    return data.trips_by_route.get(route_id, [])


@app.get("/get_trip_stoptimes", response_model=list[StopTime], operation_id="get_trip_stoptimes")
def get_trip_stoptimes(
    trip_id: str = Query(description="GTFS trip_id, e.g. ASP26GEN-1038-Sunday-00_000600_1..S03R"),
) -> list[StopTime]:
    """Get the stop times (schedule) of a trip, in stop order."""
    data = gtfs.load_data()
    stop_times = data.stop_times_by_trip.get(trip_id)
    if stop_times is None:
        raise HTTPException(status_code=404, detail=f"Unknown trip id: {trip_id}")
    return stop_times


@app.get("/get_next_trips", response_model=list[NextTrip], operation_id="get_next_trips")
def get_next_trips(
    station_id: str = Query(description="GTFS stop_id of a parent station, e.g. 101"),
    time: str = Query(
        pattern=gtfs.GTFS_TIME_PATTERN,
        description="Local time HH:MM:SS; returns trips arriving at or after it",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of trips to return",
    ),
) -> list[NextTrip]:
    """Get upcoming trips at a station after the given time, soonest first."""
    data = gtfs.load_data()
    try:
        return data.next_trips(station_id, time, limit)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown station id: {station_id}") from None