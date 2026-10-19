# GB power cut archive

Every GB distribution network operator publishes a live feed of current power cuts, but once supply is
restored the record disappears from public view. This project polls those feeds, normalises them into
one schema, and keeps the full lifecycle of every incident, so there is a public, cross-DNO history of
outages to analyse.

Status: early development.

## Layout

```
src/powercut_archive/
    models.py      the common OutageRecord every DNO feed is normalised into
    adapters/      one adapter per DNO feed
tests/
    fixtures/      saved samples of real feeds, used as test data
```

## Development

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
