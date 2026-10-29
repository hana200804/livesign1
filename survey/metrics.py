"""Thống kê khảo sát. Ảnh đi qua không được coi là bằng chứng nhìn thấy biển."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import UTC, datetime

from .geometry import PointIndex, point, polyline_distance_m, sample_line


def captured_year(value: int | str) -> int:
    if isinstance(value, bool):
        raise ValueError("captured_at không được là boolean.")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("captured_at phải hữu hạn.")
        # Graph API trả Unix epoch milliseconds; không tự đoán giây.
        return datetime.fromtimestamp(value / 1000, tz=UTC).year
    timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("captured_at phải có timezone.")
    return timestamp.astimezone(UTC).year


def normalize_images(raw: list[dict], years: list[int]) -> list[dict]:
    images = {}
    for item in raw:
        image_id = str(item.get("id", ""))
        if not image_id:
            raise ValueError("Ảnh thiếu ID.")
        year = captured_year(item["captured_at"])
        if year not in years:
            continue
        geometry = item.get("computed_geometry") or item.get("geometry")
        if not geometry or geometry.get("type") != "Point":
            raise ValueError("Ảnh thiếu tọa độ Point.")
        longitude, latitude = point(geometry["coordinates"])
        creator = item.get("creator")
        creator_id = str(creator["id"]) if isinstance(creator, dict) and creator.get("id") else None
        sequence = item.get("sequence")
        sequence_id = sequence.get("id") if isinstance(sequence, dict) else sequence
        parameters = item.get("camera_parameters")
        known_parameters = (
            isinstance(parameters, list)
            and len(parameters) > 0
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in parameters
            )
        )
        image = {
            "id": image_id,
            "captured_at": item["captured_at"],
            "year": year,
            "lon": longitude,
            "lat": latitude,
            "creator_id": creator_id,
            "sequence_id": str(sequence_id) if sequence_id else None,
            "camera_type": item.get("camera_type"),
            "has_camera_parameters": known_parameters if "camera_parameters" in item else None,
            "has_thumb_2048_url": bool(item.get("thumb_2048_url"))
            if "thumb_2048_url" in item
            else None,
            "width": item.get("width"),
            "height": item.get("height"),
        }
        if image_id in images and images[image_id] != image:
            raise ValueError("Cùng image_id có metadata mâu thuẫn; cần tải lại corpus.")
        images[image_id] = image
    return [images[key] for key in sorted(images)]


def counts(images: list[dict]) -> dict:
    creators = {row["creator_id"] for row in images if row["creator_id"]}
    pairs = {(row["creator_id"], row["year"]) for row in images if row["creator_id"]}
    return {
        "image_count": len(images),
        "sequence_count": len({row["sequence_id"] for row in images if row["sequence_id"]}),
        "creator_count": len(creators),
        "creator_year_pair_count": len(pairs),
        "missing_creator_images": sum(row["creator_id"] is None for row in images),
    }


def coverage(
    images: list[dict],
    lines: list[list[tuple[float, float]]],
    years: list[int],
    radius_m: float,
    step_m: float,
) -> dict:
    indices = {
        year: PointIndex(
            [((image["lon"], image["lat"]), image) for image in images if image["year"] == year]
        )
        for year in years
    }
    length = 0.0
    multi_year = 0.0
    by_year = {year: 0.0 for year in years}
    for line in lines:
        for location, weight in sample_line(line, step_m):
            observed_years = {
                year for year in years if indices[year].any_within(location, radius_m)
            }
            length += weight
            if len(observed_years.intersection(years)) >= 2:
                multi_year += weight
            for year in years:
                if year in observed_years:
                    by_year[year] += weight
    return {
        "road_length_m": round(length, 3),
        "covered_at_least_2_years_m": round(multi_year, 3),
        "covered_at_least_2_years_pct": round(100 * multi_year / length, 3) if length else None,
        "covered_length_m_by_year": {str(year): round(value, 3) for year, value in by_year.items()},
        "method": "weighted_midpoint_sampling",
        "sample_step_m": step_m,
        "radius_m": radius_m,
    }


def region_rows(
    region_id: str, bbox: list[float], images: list[dict], years: list[int], coverage_result: dict
) -> list[dict]:
    west, south, east, north = bbox
    inside = [
        image for image in images if west <= image["lon"] <= east and south <= image["lat"] <= north
    ]
    return [
        {
            "region": region_id,
            "year": year,
            **counts([image for image in inside if image["year"] == year]),
            "road_length_m": coverage_result["road_length_m"],
            "covered_length_m": coverage_result["covered_length_m_by_year"][str(year)],
            "covered_at_least_2_years_pct": coverage_result["covered_at_least_2_years_pct"],
        }
        for year in years
    ]


def route_images(route: dict, images: list[dict], radius_m: float) -> list[dict]:
    line = [point(value) for value in route["geometry"]["coordinates"]]
    return [
        image
        for image in images
        if polyline_distance_m((image["lon"], image["lat"]), line) <= radius_m
    ]


def route_quality(route: dict, images: list[dict], years: list[int], radius_m: float) -> list[dict]:
    passing = route_images(route, images, radius_m)
    rows = []
    for year in years:
        subset = [image for image in passing if image["year"] == year]
        parameters_known = [row for row in subset if row["has_camera_parameters"] is not None]
        thumbnails_known = [row for row in subset if row["has_thumb_2048_url"] is not None]
        camera_types_known = [row for row in subset if row["camera_type"] is not None]
        rows.append(
            {
                "route": route["properties"]["id"],
                "year": year,
                **counts(subset),
                "thumb_metadata_checked_images": len(thumbnails_known),
                "thumb_2048_url_pct": round(
                    100
                    * sum(row["has_thumb_2048_url"] for row in thumbnails_known)
                    / len(thumbnails_known),
                    3,
                )
                if thumbnails_known
                else None,
                "camera_type_checked_images": len(camera_types_known),
                "panorama_pct": round(
                    100
                    * sum(row["camera_type"] == "spherical" for row in camera_types_known)
                    / len(camera_types_known),
                    3,
                )
                if camera_types_known
                else None,
                "camera_metadata_checked_images": len(parameters_known),
                "camera_parameters_pct": round(
                    100
                    * sum(row["has_camera_parameters"] for row in parameters_known)
                    / len(parameters_known),
                    3,
                )
                if parameters_known
                else None,
                "verified_2048_pct": None,
                "bbox_size_status": "cần đo",
            }
        )
    return rows


def feature_rows(
    route: dict, features: list[dict], images: list[dict], years: list[int], radius_m: float
) -> list[dict]:
    line = [point(value) for value in route["geometry"]["coordinates"]]
    index = PointIndex([((image["lon"], image["lat"]), image) for image in images])
    rows = []
    seen_ids = set()
    for feature in features:
        feature_id = str(feature["id"])
        if feature_id in seen_ids:
            raise ValueError("Danh sách feature còn ID trùng.")
        seen_ids.add(feature_id)
        location = point(feature["geometry"]["coordinates"])
        if polyline_distance_m(location, line) > radius_m:
            continue
        passing = index.within(location, radius_m)
        for year in years:
            subset = [image for image in passing if image["year"] == year]
            rows.append(
                {
                    "route": route["properties"]["id"],
                    "feature_id": feature_id,
                    "hint_label": feature.get("object_value", "unknown"),
                    "year": year,
                    "lon": location[0],
                    "lat": location[1],
                    **counts(subset),
                    "interpretation": "passing_images_only_not_seen_evidence",
                }
            )
    return rows


def summarize_hints(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["route"], row["hint_label"], int(row["year"])].append(row)
    return [
        {
            "route": route,
            "hint_label": label,
            "year": year,
            "feature_hint_count": len(group),
            "hints_with_passing_images": sum(int(row["image_count"]) > 0 for row in group),
            "hints_with_ge2_passing_creators": sum(int(row["creator_count"]) >= 2 for row in group),
            "passing_creator_count_median": statistics.median(
                int(row["creator_count"]) for row in group
            ),
            "passing_creator_count_max": max(int(row["creator_count"]) for row in group),
            "manual_class_confirmation": "pending",
            "interpretation": "mapillary_hint_not_ground_truth",
        }
        for (route, label, year), group in sorted(groups.items())
    ]
