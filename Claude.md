# GB power cut archive

Polls GB DNOs' live power cut feeds, normalises them into one schema, and keeps
the full lifecycle of every incident (first seen, ETR revisions, restored), so
there's a public cross-DNO outage history. Portfolio project aimed at senior
DNO engineers. Goal is to run it live.

## How we work
- Claude writes the code, I review it. Work in small steps, one per session.
- For every step: show me the code in the chat and explain the reasoning behind
  the key decisions. Don't just say "done".
- Run `pytest` before saying a step is finished. Commit only when I say so.

## Code style
- Write like an intermediate Python developer, not AI-generated code.
- Short comments, only where the *why* isn't obvious. No long docstrings,
  section banners or `#:` comments.
- Plain names (`to_int`, `get_rows`). Type hints on dataclass fields; light
  elsewhere.
- No extra classes or abstraction unless there's a real need.
- Match the style of `models.py` and `adapters/base.py`.

## Rules the code must keep
- All datetimes in `OutageRecord` are UTC. Adapters convert at the boundary
  using `to_utc`, and must decide from REAL data whether a naive timestamp is
  UK local time or a fixed offset.
- `raw` keeps the untouched source row and is excluded from equality.
- Adapters only parse (`get_rows`, `parse_row`). HTTP fetching lives elsewhere.
- A bad row is collected in `ParseResult.errors`, never allowed to kill a poll.
- Unknown status values map to `Status.UNKNOWN`, never a guess.
- Build adapters against saved samples in `tests/fixtures/`, not docs alone.
- Public data only. Nothing from my employer's internal systems.

## Stack and roadmap
Python, pytest. Later: Postgres, Docker Compose, Alembic, dbt, DuckDB/Parquet,
GitHub Actions. No Kafka, Spark, Airflow or cloud warehouses: this is small
data, and the hard part is reliability, not scale.

1. Done: `OutageRecord` model
2. Done: adapter interface and parsing helpers (`adapters/base.py`)
3. NGED and Northern Powergrid adapters, tested on real samples
4. Fetcher: HTTP with timeouts and retries; saves raw payloads
5. Lifecycle engine: compare polls, detect new / changed / restored /
   disappeared incidents
6. Storage: Postgres plus Docker Compose; bronze (raw snapshots, store only
   on change), silver (incidents), gold (metrics)
7. Scheduler loop running the collector continuously
8. Remaining DNOs: UKPN, SSEN, SPEN, ENWL
9. Monitoring: per-DNO freshness and error-rate alerts, schema-drift detection
10. dbt models for metrics (ETR accuracy, restoration times, repeat-hit areas)
11. Deploy to a small cloud server
12. API, dashboard and public dataset downloads

## Feeds
- NGED (detailed live power cuts): https://connecteddata.nationalgrid.co.uk/api/3/action/datastore_search?resource_id=a1365982-4e05-463c-8304-8323a2ba0ccd&limit=1000
- Northern Powergrid: https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog/datasets/live-power-cuts-data/exports/json

TODO: both timezone decisions below come from a BST sample (19 Oct 2026),
where UK local and a fixed UTC+1 look identical. Re-check both feeds with
samples taken after the clocks go back on 25 Oct 2026.

Decisions for both feeds:
- `customers_off` is confirmed customers only; the DNO's predicted extra
  customers go in `customers_predicted_off`.
- `postcode` is every postcode, whitespace-collapsed, de-duplicated, sorted
  and joined with ", ", so reordering between polls isn't a change.

NGED (`adapters/nged.py`):
- One row per incident in `result.records`; key is `fault_id`.
- Naive timestamps are UK local time (Europe/London).
- Status: "In Progress" -> IN_PROGRESS, "Awaiting" -> AWAITING, else UNKNOWN.
  No restored rows seen; restored incidents seem to just drop out.
- `etr` is used when present; when empty (always, for planned work) it falls
  back to `planned_outage_end_date`.
- Blanks are a mix of `null` and `""`.

Northern Powergrid (`adapters/npg.py`):
- One row per affected postcode, not per incident. `get_rows` groups rows by
  `reference` into `{"reference", "rows"}` so each incident gives one record;
  `raw` holds all its source rows.
- Timestamps say `+00:00` but are UK local time: in the sample, updatedate
  reached 21:20+00:00 on a feed saved at 20:26 UTC. The offset is stripped and
  the time read as Europe/London. Any other offset is a row error.
- Status from `incidentstatus`: 5 -> IN_PROGRESS, 6 -> RESTORED, else
  UNKNOWN. 6 comes with isaffected=0 and a frozen updatedate; the customer
  message isn't reliable (closed faults still say "team has arrived").
- `planned` is `natureofoutage == "Planned Work on System"`.
- `voltage`: HV_N/HV_S -> HV; anything else passes through unchanged.
- `etr` is `estimatedtimetillresolution`; the ±30 min range stays in raw.
- lat/lon is the average of the rows' points, rounded to 5 decimal places.
- Postcodes with short outward codes are padded ("BD6  1BJ").