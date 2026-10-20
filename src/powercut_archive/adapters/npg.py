from datetime import datetime, timedelta

from powercut_archive.adapters.base import (
    Adapter,
    clean,
    join_postcodes,
    to_float,
    to_int,
    to_utc,
)
from powercut_archive.models import OutageRecord, Status

# incidentstatus 6 always comes with isaffected=0 and a frozen updatedate, and
# planned jobs at 6 say "The scheduled work has now been completed".
STATUSES = {
    "5": Status.IN_PROGRESS,
    "6": Status.RESTORED,
}

VOLTAGES = {
    "HV_N": "HV",
    "HV_S": "HV",
}


def to_utc_npg(value):
    # NPG labels its times +00:00, but they are actually UK local time. In a
    # BST sample, updatedate values were stamped 21:20+00:00 on a feed we'd
    # saved at 20:26 UTC, which is impossible if +00:00 were true. So we drop
    # the label and treat the time as Europe/London. This is deliberate, not
    # a bug. If NPG ever sends a different offset, fail loudly instead of
    # guessing what it means.
    value = clean(value)
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() not in (None, timedelta(0)):
        raise ValueError(f"Unexpected offset in NPG timestamp {value!r}")
    return to_utc(dt.replace(tzinfo=None).isoformat())


class NPGAdapter(Adapter):
    dno = "NPG"
    url = (
        "https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog"
        "/datasets/live-power-cuts-data/exports/json"
    )

    def get_rows(self, payload):
        # The feed has one row per affected postcode, not per incident, so
        # combine them first or parse() would emit duplicate keys.
        groups = {}
        for row in payload:
            groups.setdefault(row.get("reference"), []).append(row)
        return [{"reference": ref, "rows": rows} for ref, rows in groups.items()]

    def parse_row(self, row, polled_at):
        rows = row["rows"]
        # Every incident-level field is identical across an incident's rows;
        # only postcode, lat/lng and area differ.
        first = rows[0]

        nature = clean(first["natureofoutage"])
        if nature is None:
            raise ValueError("natureofoutage is blank")

        status = STATUSES.get(clean(first["incidentstatus"]), Status.UNKNOWN)

        voltage = clean(first["type"])
        voltage = VOLTAGES.get(voltage, voltage)

        postcodes = []
        for r in rows:
            postcode = r["postcode"] or []
            if isinstance(postcode, str):
                postcode = [postcode]
            postcodes.extend(postcode)

        points = [(to_float(r["lat"]), to_float(r["lng"])) for r in rows]
        points = [(lat, lon) for lat, lon in points if lat is not None and lon is not None]
        lat = lon = None
        if points:
            # Rounded so float noise from row order doesn't count as a change.
            lat = round(sum(p[0] for p in points) / len(points), 5)
            lon = round(sum(p[1] for p in points) / len(points), 5)

        return OutageRecord(
            dno=self.dno,
            source_id=clean(row["reference"]),
            polled_at=polled_at,
            planned=nature == "Planned Work on System",
            status=status,
            category=clean(first["powercutcategory"]),
            voltage=voltage,
            customers_off=to_int(first["totalconfirmedpowercut"]),
            customers_predicted_off=to_int(first["totalpredictedpowercut"]),
            reported_at=to_utc_npg(first["loggedtime"]),
            etr=to_utc_npg(first["estimatedtimetillresolution"]),
            postcode=join_postcodes(postcodes),
            lat=lat,
            lon=lon,
            raw=row,
        )
