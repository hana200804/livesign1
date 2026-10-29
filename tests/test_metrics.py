from datetime import UTC, datetime

import pytest

from survey.metrics import (
    captured_year,
    counts,
    coverage,
    feature_rows,
    normalize_images,
    route_quality,
)


def raw_image(identity="a", year=2023, creator="u", sequence="s", longitude=105.85):
    return {
        "id": identity,
        "captured_at": int(datetime(year, 1, 1, tzinfo=UTC).timestamp() * 1000),
        "creator": {"id": creator} if creator else None,
        "sequence": sequence,
        "geometry": {"type": "Point", "coordinates": [longitude, 21.03]},
    }


def route():
    return {
        "properties": {"id": "candidate"},
        "geometry": {"type": "LineString", "coordinates": [[105.85, 21.03], [105.851, 21.03]]},
    }


def test_uses_captured_at_utc_and_rejects_future():
    records = [raw_image("a", 2023), raw_image("b", 2024), raw_image("c", 2026)]
    assert [row["year"] for row in normalize_images(records, [2023, 2024, 2025])] == [2023, 2024]
    assert captured_year("2024-01-01T00:30:00+07:00") == 2023
    assert captured_year("2026-01-01T00:00:00Z") == 2026


@pytest.mark.parametrize("timestamp", [True, "2023-01-01T00:00:00", float("nan")])
def test_rejects_ambiguous_timestamps(timestamp):
    with pytest.raises(ValueError):
        captured_year(timestamp)


def test_hundreds_of_sequences_are_not_independent_photographers():
    images = normalize_images(
        [raw_image(str(index), sequence=str(index)) for index in range(100)], [2023]
    )
    assert counts(images) == {
        "image_count": 100,
        "sequence_count": 100,
        "creator_count": 1,
        "creator_year_pair_count": 1,
        "missing_creator_images": 0,
    }


def test_pairs_are_distinct_by_creator_and_year():
    images = normalize_images(
        [raw_image("a"), raw_image("b", 2024), raw_image("c", creator=None)], [2023, 2024]
    )
    result = counts(images)
    assert result["creator_count"] == 1
    assert result["creator_year_pair_count"] == 2
    assert result["missing_creator_images"] == 1


def test_conflicting_duplicate_image_id_stops_pipeline():
    with pytest.raises(ValueError, match="mâu thuẫn"):
        normalize_images([raw_image("a"), raw_image("a", creator="another")], [2023])


def test_weighted_coverage_requires_two_distinct_years():
    images = normalize_images([raw_image("a"), raw_image("b"), raw_image("c", 2024)], [2023, 2024])
    lines = [[(105.8499, 21.03), (105.8501, 21.03)]]
    measured = coverage(images, lines, [2023, 2024], 30, 3)
    assert measured["covered_at_least_2_years_pct"] == 100
    single = coverage(images[:2], lines, [2023, 2024], 30, 3)
    assert single["covered_at_least_2_years_pct"] == 0
    assert measured["road_length_m"] > 20


def test_missing_metadata_is_unknown_not_zero_percent():
    images = normalize_images([raw_image()], [2023])
    rows = route_quality(route(), images, [2023, 2024], 30)
    assert rows[0]["camera_parameters_pct"] is None
    assert rows[0]["thumb_2048_url_pct"] is None
    assert rows[0]["panorama_pct"] is None
    assert rows[1]["image_count"] == 0
    assert rows[1]["panorama_pct"] is None


def test_feature_years_include_zero_and_ignore_first_seen():
    images = normalize_images([raw_image()], [2023, 2024, 2025])
    feature = {
        "id": "sign",
        "object_value": "hint_only",
        "first_seen_at": "2025-01-01T00:00:00Z",
        "geometry": {"type": "Point", "coordinates": [105.85, 21.03]},
    }
    rows = feature_rows(route(), [feature], images, [2023, 2024, 2025], 30)
    assert [row["image_count"] for row in rows] == [1, 0, 0]
    assert all(row["interpretation"] == "passing_images_only_not_seen_evidence" for row in rows)
