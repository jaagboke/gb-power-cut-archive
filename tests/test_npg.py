import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from powercut_archive.adapters.npg import NPGAdapter
from powercut_archive.models import Status

FIXTURE = Path(__file__).parent / "fixtures" / "npg_20261019T2120.json"
# The fixture file was written at 20:26 UTC (21:26 BST)
POLLED_AT = datetime(2026, 10, 19, 20, 26, tzinfo=timezone.utc)
UTC = timezone.utc


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def parse(payload):
    return NPGAdapter().parse(payload, POLLED_AT)


def by_id(result):
    return {r.source_id: r for r in result.records}


def rows_for(payload, reference):
    return [r for r in payload if r["reference"] == reference]


def test_rows_are_grouped_into_one_record_per_incident(payload):
    result = parse(payload)
    assert result.errors == []
    assert len(payload) == 431
    assert len(result.records) == 48


def test_record_keys_are_unique(payload):
    keys = [r.key for r in parse(payload).records]
    assert len(keys) == len(set(keys))


def test_unplanned_fault_maps_all_fields(payload):
    record = by_id(parse(payload))["INCD-825641-A"]
    assert record.dno == "NPG"
    assert record.planned is False
    assert record.status == Status.IN_PROGRESS
    assert record.category == "U/G LV Mains Repair (Other)"
    assert record.voltage == "LV"
    assert record.customers_off == 117
    assert record.customers_predicted_off == 0
    assert record.customers_restored is None
    assert record.restored_at is None
    assert record.postcode == "LS2 7DH, LS2 7PN, LS2 7QW, LS2 8JS, LS27 0EX"


def test_padded_postcodes_are_normalised(payload):
    record = by_id(parse(payload))["INCD-825641-A"]
    raw_postcodes = [r["postcode"][0] for r in record.raw["rows"]]
    assert "LS2  7DH" in raw_postcodes
    assert "LS2 7DH" in record.postcode.split(", ")


def test_plus_zero_offset_is_read_as_uk_local_time(payload):
    record = by_id(parse(payload))["INCD-825641-A"]
    assert record.raw["rows"][0]["loggedtime"] == "2026-10-19T11:10:00+00:00"
    assert record.reported_at == datetime(2026, 10, 19, 10, 10, tzinfo=UTC)
    assert record.etr == datetime(2026, 10, 19, 22, 59, tzinfo=UTC)


def test_no_timestamp_is_after_the_poll(payload):
    # Taking +00:00 at face value would put the newest faults 50 minutes in
    # the future. This is the evidence for the UK-local reading.
    for record in parse(payload).records:
        assert record.reported_at <= POLLED_AT


def test_winter_time_is_treated_as_gmt(payload):
    for row in rows_for(payload, "INCD-825641-A"):
        row["loggedtime"] = "2026-12-01T10:00:00+00:00"
    record = by_id(parse(payload))["INCD-825641-A"]
    assert record.reported_at == datetime(2026, 12, 1, 10, 0, tzinfo=UTC)


def test_unexpected_offset_is_an_error_not_a_guess(payload):
    for row in rows_for(payload, "INCD-825641-A"):
        row["loggedtime"] = "2026-10-19T11:10:00+01:00"
    result = parse(payload)
    assert len(result.records) == 47
    assert "Unexpected offset" in result.errors[0][1]


def test_big_incident_combines_all_postcodes(payload):
    record = by_id(parse(payload))["INCD-825846-A"]
    assert len(record.raw["rows"]) == 153
    postcodes = record.postcode.split(", ")
    assert len(postcodes) == 153
    assert postcodes == sorted(postcodes)


def test_duplicate_postcode_is_listed_once(payload):
    # PPCR80193 spans two areas and lists YO17 8DB in both
    record = by_id(parse(payload))["PPCR80193"]
    assert len(record.raw["rows"]) == 22
    assert record.postcode.count("YO17 8DB") == 1
    assert len(record.postcode.split(", ")) == 21


def test_location_is_rounded_average_of_rows(payload):
    record = by_id(parse(payload))["INCD-825846-A"]
    rows = record.raw["rows"]
    assert record.lat == round(sum(r["lat"] for r in rows) / len(rows), 5)
    assert record.lon == round(sum(r["lng"] for r in rows) / len(rows), 5)


def test_row_order_does_not_change_the_record(payload):
    forwards = by_id(parse(payload))
    backwards = by_id(parse(list(reversed(payload))))
    assert forwards == backwards


def test_completed_planned_work_is_restored(payload):
    record = by_id(parse(payload))["PPCR80468"]
    assert record.planned is True
    assert record.status == Status.RESTORED
    assert record.customers_off == 357


def test_live_planned_work_is_in_progress(payload):
    record = by_id(parse(payload))["PPCR80261"]
    assert record.planned is True
    assert record.status == Status.IN_PROGRESS


def test_unknown_incident_status(payload):
    for row in rows_for(payload, "INCD-825641-A"):
        row["incidentstatus"] = 9
    assert by_id(parse(payload))["INCD-825641-A"].status == Status.UNKNOWN


def test_hv_subtypes_map_to_hv(payload):
    records = by_id(parse(payload))
    assert records["INCD-825631-A"].raw["rows"][0]["type"] == "HV_S"
    assert records["INCD-825631-A"].voltage == "HV"
    assert {r.voltage for r in records.values()} == {"HV", "LV"}


def test_unrecognised_voltage_passes_through(payload):
    for row in rows_for(payload, "INCD-825641-A"):
        row["type"] = "EHV"
    assert by_id(parse(payload))["INCD-825641-A"].voltage == "EHV"


def test_missing_etr_is_none(payload):
    record = by_id(parse(payload))["INCD-825631-A"]
    assert record.etr is None


def test_bad_incident_is_collected_without_losing_the_rest(payload):
    for row in rows_for(payload, "INCD-825641-A"):
        row["totalconfirmedpowercut"] = "lots"
    result = parse(payload)
    assert len(result.records) == 47
    assert len(result.errors) == 1
