"""Đầu vào tổng hợp chỉ dùng trong test; không đưa vào báo cáo khảo sát thật."""

import pytest

from survey.__main__ import collection_spec
from survey.io import sha256_file, stable_hash, write_json, write_jsonl


@pytest.fixture
def report_case(tmp_path):
    config = {
        "years": [2023, 2024, 2025],
        "regions": {"hoan_kiem": {"bbox": [105.84, 21.02, 105.86, 21.04]}},
        "route_seeds": [],
    }
    params = {
        "survey_radius_m": {"value": 30, "status": "đã chốt"},
        "road_sample_step_m": {"value": 10, "status": "dự kiến"},
    }
    write_json(tmp_path / "config/survey.yaml", config)
    write_json(tmp_path / "config/params.yaml", params)
    cache = tmp_path / "data/cache/hoan_kiem"
    osm = {
        "elements": [
            {
                "type": "way",
                "id": 1,
                "nodes": [1, 2],
                "tags": {"highway": "residential"},
                "geometry": [{"lon": 105.85, "lat": 21.03}, {"lon": 105.851, "lat": 21.03}],
            }
        ]
    }
    write_json(cache / "osm.json", osm)
    write_json(
        cache / "osm-manifest.json",
        {
            "bbox": config["regions"]["hoan_kiem"]["bbox"],
            "data_sha256": sha256_file(cache / "osm.json"),
        },
    )
    image = {
        "id": "fixture",
        "captured_at": "2023-01-01T00:00:00Z",
        "creator": {"id": "person"},
        "geometry": {"type": "Point", "coordinates": [105.85, 21.03]},
        "sequence": "sequence",
    }
    write_jsonl(cache / "images.jsonl", [image])
    write_jsonl(cache / "features.jsonl", [])
    for kind in ("images", "features"):
        spec = collection_spec(config, params, "hoan_kiem", kind)
        write_json(
            cache / f"{kind}-manifest.json",
            {
                "status": "complete",
                "query_spec_hash": stable_hash(spec),
                "data_sha256": sha256_file(cache / f"{kind}.jsonl"),
            },
        )
    return tmp_path, config, params
