"""Khóa mẫu ảnh để đo chất lượng và chuẩn bị gán bbox; không tạo ground truth tự động."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from .datasets import image_dimensions
from .io import read_json, read_jsonl, sha256_file, stable_hash, write_csv, write_json, write_jsonl
from .metrics import captured_year, normalize_images, route_images
from .network import IMAGE_FIELDS, Mapillary, SurveyError, canonical_id


def select_sample(images: list[dict], years: list[int], per_year: int, seed: str) -> list[dict]:
    if per_year < 1:
        raise ValueError("Mỗi năm cần ít nhất 1 ảnh trong mẫu.")
    result = []
    for year in years:
        subset = [image for image in images if image["year"] == year]
        subset.sort(key=lambda image: stable_hash([seed, image["id"]]))
        result.extend(subset[:per_year])
    return result


def collect_samples(root: Path, config: dict, params: dict, per_year: int) -> None:
    client = Mapillary()
    selected = {}
    membership = defaultdict(set)
    for seed in config["route_seeds"]:
        route_path = root / "reports/stage0/routes" / f"{seed['id']}.geojson"
        if not route_path.exists():
            continue
        raw = read_jsonl(root / "data/cache" / seed["region"] / "images.jsonl")
        images = normalize_images(raw, config["years"])
        passing = route_images(read_json(route_path), images, params["survey_radius_m"]["value"])
        for image in select_sample(passing, config["years"], per_year, "livesign-stage0-v1"):
            selected[image["id"]] = image
            membership[image["id"]].add(seed["id"])
    if not selected:
        raise SurveyError("Chưa có tuyến/ảnh hợp lệ để khóa mẫu.")
    output = root / "data/private/samples"
    # Khóa ID trước khi tải detector hoặc chạy dự đoán.
    locked = [
        {
            "image_id": image_id,
            "year": selected[image_id]["year"],
            "creator_id": selected[image_id]["creator_id"],
            "routes": sorted(membership[image_id]),
        }
        for image_id in sorted(selected)
    ]
    lock_hash = stable_hash(locked)
    existing = output / "sample-lock.json"
    if existing.exists() and read_json(existing)["sample_ids_hash"] != lock_hash:
        raise SurveyError(
            "Mẫu đã khóa khác lựa chọn hiện tại. Cần lưu phiên bản mẫu cũ trước khi đổi."
        )
    write_json(
        existing,
        {
            "sample_ids_hash": lock_hash,
            "images": locked,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "purpose": "stage0_quality_and_detector_poc_not_hanoi_test_set",
        },
    )
    rows, failures = [], []
    for item in locked:
        image_id = canonical_id(item["image_id"])
        details_path = output / "metadata" / f"{image_id}.json"
        image_path = output / "images" / f"{image_id}.jpg"
        try:
            if details_path.exists():
                details = read_json(details_path)
            else:
                details = client.http.json(
                    f"https://graph.mapillary.com/{image_id}?"
                    + urlencode({"fields": IMAGE_FIELDS}),
                    token=client.token,
                )
                if (
                    str(details.get("id")) != image_id
                    or captured_year(details["captured_at"]) != item["year"]
                ):
                    raise SurveyError("Metadata ảnh khác mẫu đã khóa.")
                write_json(details_path, details)
            thumbnail = details.get("thumb_2048_url")
            if not thumbnail:
                raise SurveyError("Ảnh không có thumb_2048_url.")
            if not image_path.exists():
                client.http.download(thumbnail, image_path, max_bytes=30 * 1024**2)
            width, height = image_dimensions(image_path)
            rows.append(
                {
                    "image_id": image_id,
                    "year": item["year"],
                    "creator_id": item["creator_id"],
                    "routes": ";".join(item["routes"]),
                    "width_px": width,
                    "height_px": height,
                    "verified_width_at_least_2048": width >= 2048,
                    "panorama": details.get("camera_type") == "spherical",
                    "has_camera_parameters": bool(details.get("camera_parameters")),
                    "image_sha256": sha256_file(image_path),
                    "manual_bbox_status": "cần gán",
                }
            )
        except (SurveyError, ValueError, KeyError) as error:
            failures.append({"image_id": image_id, "reason": str(error)})
    report = root / "reports/stage0"
    if rows:
        write_csv(report / "sample-quality.csv", list(rows[0]), rows)
    write_json(
        report / "sample-manifest.json",
        {
            "sample_ids_hash": lock_hash,
            "requested_images": len(locked),
            "downloaded_and_verified_images": len(rows),
            "failures": failures,
            "per_route_year_target_images": per_year,
            "ground_truth_status": "not_annotated",
            "detector_status": "not_run",
        },
    )
    write_jsonl(
        output / "annotation-template.jsonl",
        [
            {
                "image_id": row["image_id"],
                "image_sha256": row["image_sha256"],
                "width_px": row["width_px"],
                "height_px": row["height_px"],
                "review_status": "pending",
                "boxes": [],
                "label_source": "manual_required",
            }
            for row in rows
        ],
    )
    print(f"Mẫu đã khóa: {len(locked)} ảnh. Đã tải và đo kích thước: {len(rows)} ảnh.")
    if failures:
        raise SurveyError("Một số ảnh mẫu chưa tải được; chưa báo mẫu hoàn chỉnh.")
