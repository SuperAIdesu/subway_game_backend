"""Mock FastAPI application exposing NYC subway GTFS data.

Implements the draft API spec using hardcoded sample data from
`mock_data.py`; no GTFS loading or scheduling logic yet. Every endpoint
returns 404 when given an id that is not part of the sample data.
"""

from fastapi import FastAPI, HTTPException, Query

from . import mock_data
from .models import NextTrip, Route, Station, StopTime, Trip

app = FastAPI(
    title="NYC Subway GTFS API (mock)",
    description=(
        "Draft API over MTA subway GTFS data: lines, stations, trips, stop times. "
        "Responses are mock data; endpoints and models are final."
    ),
    version="0.1.0",
)


@app.get("/", operation_id="health")
def root() -> dict[str, str]:
    return {"status": "ok", "spec": "/docs"}


@app.get("/get_station", response_model=Station, operation_id="get_station")
def get_station(
    station_id: str = Query(description="GTFS stop_id of a parent station, e.g. 101"),
) -> Station:
    """Get a single station, including the lines it is on."""
    station = mock_data.STATIONS.get(station_id)
    if station is None:
        raise HTTPException(status_code=404, detail=f"Unknown station id: {station_id}")
    return station


@app.get("/get_route", response_model=Route, operation_id="get_route")
def get_route(
    route_id: str = Query(description="GTFS route_id, e.g. 1 or A"),
) -> Route:
    """Get a single line (route)."""
    route = mock_data.ROUTES.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Unknown route id: {route_id}")
    return route


@app.get("/get_route_stations", response_model=list[Station], operation_id="get_route_stations")
def get_route_stations(
    route_id: str = Query(description="GTFS route_id, e.g. 1 or A"),
) -> list[Station]:
    """Get the ordered list of stations that a line contains."""
    if route_id not in mock_data.ROUTES:
        raise HTTPException(status_code=404, detail=f"Unknown route id: {route_id}")
    station_ids = mock_data.ROUTE_STATIONS.get(route_id, [])
    return [mock_data.STATIONS[s] for s in station_ids]


@app.get("/get_trips", response_model=list[Trip], operation_id="get_trips")
def get_trips(
    route_id: str = Query(description="GTFS route_id, e.g. 1 or A"),
) -> list[Trip]:
    """Get the list of trips for a line."""
    if route_id not in mock_data.ROUTES:
        raise HTTPException(status_code=404, detail=f"Unknown route id: {route_id}")
    return mock_data.TRIPS.get(route_id, [])


@app.get("/get_trip_stoptimes", response_model=list[StopTime], operation_id="get_trip_stoptimes")
def get_trip_stoptimes(
    trip_id: str = Query(description="GTFS trip_id, e.g. ASP26GEN-1038-Sunday-00_000600_1..S03R"),
) -> list[StopTime]:
    """Get the stop times (schedule) of a trip, in stop order."""
    stop_times = mock_data.STOP_TIMES.get(trip_id)
    if stop_times is None:
        raise HTTPException(status_code=404, detail=f"Unknown trip id: {trip_id}")
    return stop_times


@app.get("/get_next_trips", response_model=list[NextTrip], operation_id="get_next_trips")
def get_next_trips(
    station_id: str = Query(description="GTFS stop_id of a parent station, e.g. 101"),
    time: str = Query(description="Local time HH:MM:SS to look up departures after"),
) -> list[NextTrip]:
    """Get upcoming trips at a station after the given time.

    Mock behavior: returns the fixed sample trips for the station and ignores
    `time`; the real implementation will filter by the requested time.
    """
    next_trips = mock_data.NEXT_TRIPS.get(station_id)
    if next_trips is None:
        raise HTTPException(status_code=404, detail=f"No trips found for station id: {station_id}")
    return next_trips