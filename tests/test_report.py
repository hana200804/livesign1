import csv

import pytest

from survey.__main__ import report
from survey.io import read_json, write_json
from survey.network import SurveyError


def test_report_exports_all_years_with_verified_input_hashes(report_case):
    root, config, params = report_case
    report(root, config, params, "hoan_kiem")
    with (root / "reports/stage0/region-coverage.csv").open(encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    assert [row["year"] for row in rows] == ["2023", "2024", "2025"]
    assert [int(row["image_count"]) for row in rows] == [1, 0, 0]
    assert all(float(row["covered_at_least_2_years_pct"]) == 0 for row in rows)
    manifest = read_json(root / "reports/stage0/survey-manifest.json")
    assert manifest["negative_evidence_enabled"] is False
    assert manifest["route_approved"] is False


def test_report_rejects_stale_osm_instead_of_reporting_wrong_region(report_case):
    root, config, params = report_case
    write_json(
        root / "data/cache/hoan_kiem/osm-manifest.json",
        {"bbox": [0, 0, 1, 1], "data_sha256": "old"},
    )
    with pytest.raises(SurveyError, match="OSM khác"):
        report(root, config, params, "hoan_kiem")
