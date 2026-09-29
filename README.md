# NYC Subway GTFS API

A FastAPI backend exposing NYC subway schedule data from the MTA's GTFS feed
(lines, stations, trips, stop times). Data is loaded into memory from
[`gtfs_subway/`](gtfs_subway) on first request.

## Requirements

- Python ≥ 3.14
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
uv sync                      # install dependencies
uv run subway-game-backend   # serve on http://127.0.0.1:8000
```

Then open <http://127.0.0.1:8000/docs> for the interactive Swagger UI.

Manual alternative:

```bash
uv run uvicorn subway_game_backend.main:app --reload
```

The first request loads and indexes the feed (~5s for the 565k-row
`stop_times.txt`); every request after that is an in-memory lookup.

## API

All endpoints return JSON. Unknown ids yield `404`; invalid parameter values
yield `422`.

| Endpoint | Query params | Returns |
|---|---|---|
| `GET /all_stations` | — | All station ids, ordered by station name |
| `GET /all_routes` | — | All route ids, in canonical MTA line order |
| `GET /get_station` | `station_id` | One station: `id`, `name`, `lat`, `lon`, `on_lines` |
| `GET /get_route` | `route_id` | One line: GTFS route fields (name, color, url, …) |
| `GET /get_route_stations` | `route_id` | Ordered stations on a line |
| `GET /get_trips` | `route_id` | Trips of a line (headsign, direction, service, shape) |
| `GET /get_trip_stoptimes` | `trip_id` | A trip's schedule in stop order |
| `GET /get_next_trips` | `station_id`, `time`, `day?`, `limit?` | Upcoming trips at a station, soonest first |

Example — next 3 trips at Times Sq on Sunday after noon:

```bash
curl "http://127.0.0.1:8000/get_next_trips?station_id=127&time=12:00:00&day=sunday&limit=3"
```

### `/get_next_trips` details

- `time` is local `HH:MM:SS`; trips arriving at or after it are returned.
- `day` filters by service calendar: `weekday` (default), `saturday` or
  `sunday`, including dated supplement calendars from `calendar.txt`.
- `limit` (1–100) caps the result; **omit it to get every remaining trip of
  the day** (can be a few hundred at a busy station).
- Responses extend plain trips with `arrival_time`, `departure_time` and
  `stop_sequence` at the requested station.
- GTFS times may exceed 24 h (e.g. `25:56:30` = 1:56:30 AM the next day).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GTFS_DATA_DIR` | `./gtfs_subway` | Feed directory; must contain the GTFS `.txt` files |

## Development

```bash
uv sync --dev
uv run pytest        # 44 tests; loads the real feed once (~20s)
```

Tests cover the loader (`tests/test_gtfs.py`) and the endpoints
(`tests/test_api.py`), including cross-checks that a trip's stop times match
its station's `next_trips` listing and that every id from `/all_stations` /
`/all_routes` resolves via the detail endpoints.

## Project layout

```
src/subway_game_backend/
├── models.py    # Pydantic response models (GTFS field naming)
├── gtfs.py      # Feed loading, parsing and indexes
└── main.py      # FastAPI app and endpoints
gtfs_subway/     # MTA subway GTFS feed (data)
tests/           # pytest suite
```

## Data notes

- Stations are GTFS *parent* stops; platform ids (`101N`/`101S`) are mapped to
  their parent, so `/get_station` takes `101`.
- Station complexes are **not** merged: e.g. the 7/N/Q/R/W platforms at Times
  Sq are separate parent stations from `127` (see `transfers.txt`).
- `on_lines` reflects the feed exactly, including express variants (`6X`,
  `7X`) and shuttle services.
- Feed version: `20260826-X-long-term-supplement-trip-ids` (see
  `gtfs_subway/feed_info.txt`); schedule dates live in `calendar.txt`.

## Data source

[MTA subway GTFS data](https://www.mta.info/developers) — static schedule
feed, published by MTA New York City Transit.
