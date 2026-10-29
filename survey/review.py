"""Xuất công cụ duyệt cục bộ. Tệp xuất chỉ thành ground truth sau khi người dùng gán."""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

from .io import read_json, read_jsonl, read_yaml, sha256_file, write_jsonl


def build_review(root: Path) -> Path:
    lock = read_json(root / "data/private/samples/sample-lock.json")
    with (root / "reports/stage0/sample-quality.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        quality = {row["image_id"]: row for row in csv.DictReader(source)}
    images = []
    for item in lock["images"]:
        row = quality.get(item["image_id"])
        if row is None:
            continue
        images.append(
            {
                **item,
                "width_px": int(row["width_px"]),
                "height_px": int(row["height_px"]),
                "image_sha256": row["image_sha256"],
            }
        )
    config = read_yaml(root / "config/survey.yaml")
    payload = {
        "sample_ids_hash": lock["sample_ids_hash"],
        "images": images,
        "routes": [{"id": row["id"], "name": row["name"]} for row in config["route_seeds"]],
    }
    template = Path(__file__).with_name("review.html").read_text(encoding="utf-8")
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    output = root / "data/private/review/routes/index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("__SURVEY_DATA__", encoded), encoding="utf-8")
    return output


def validate_manual_record(row: dict, expected: dict) -> dict:
    if row.get("image_sha256") != expected["image_sha256"]:
        raise ValueError("Hash ảnh gán tay khác ảnh đã khóa.")
    if row.get("review_status") not in ("pending", "reviewed", "unclear"):
        raise ValueError("Trạng thái duyệt không hợp lệ.")
    width, height = expected["width_px"], expected["height_px"]
    if (row.get("width_px"), row.get("height_px")) != (width, height):
        raise ValueError("Kích thước ảnh gán tay không khớp.")
    boxes = row.get("boxes")
    if not isinstance(boxes, list) or len(boxes) > 200:
        raise ValueError("Ảnh cần danh sách bbox tối đa 200 biển.")
    for box in boxes:
        if not isinstance(box.get("label"), str) or not re.fullmatch(
            r"(?:DP|P|W|I|R|S)\.\d{3}[a-z]?", box["label"]
        ):
            raise ValueError("Mã QCVN gán tay không đúng định dạng.")
        coordinates = box.get("bbox_xyxy")
        if (
            not isinstance(coordinates, list)
            or len(coordinates) != 4
            or not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in coordinates
            )
        ):
            raise ValueError("BBox gán tay cần 4 tọa độ px hữu hạn.")
        x1, y1, x2, y2 = coordinates
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError("BBox gán tay vượt biên hoặc không có diện tích.")
    if row["review_status"] == "reviewed":
        if not boxes and row.get("explicit_empty") is not True:
            raise ValueError("Ảnh không có bbox cần xác nhận rỗng rõ ràng; không tự coi đã duyệt.")
        if boxes and row.get("explicit_empty"):
            raise ValueError("Ảnh có bbox không thể cùng lúc xác nhận rỗng.")
        if row.get("label_source") != "manual":
            raise ValueError("Ground truth cần nguồn gán tay.")
    return {
        "image_id": expected["image_id"],
        "image_sha256": expected["image_sha256"],
        "width_px": width,
        "height_px": height,
        "review_status": row["review_status"],
        "explicit_empty": row.get("explicit_empty") is True,
        "boxes": boxes,
        "label_source": "manual",
    }


def import_review(root: Path, path: Path) -> int:
    exported = read_json(path)
    lock = read_json(root / "data/private/samples/sample-lock.json")
    if (
        exported.get("sample_ids_hash") != lock["sample_ids_hash"]
        or exported.get("annotation_origin") != "human_review_ui"
    ):
        raise ValueError("Tệp duyệt không thuộc mẫu đã khóa hoặc không có nguồn gán tay.")
    expected = {
        row["image_id"]: row
        for row in read_jsonl(root / "data/private/samples/annotation-template.jsonl")
    }
    accepted = []
    seen = set()
    for row in exported["images"]:
        identity = row.get("image_id")
        if identity not in expected or identity in seen:
            raise ValueError("Tệp duyệt có ID ảnh lạ hoặc trùng.")
        seen.add(identity)
        if row.get("review_status") == "pending":
            continue
        actual_hash = sha256_file(root / "data/private/samples/images" / f"{identity}.jpg")
        if actual_hash != expected[identity]["image_sha256"]:
            raise ValueError("Tệp ảnh đã đổi sau khi khóa mẫu.")
        accepted.append(validate_manual_record(row, expected[identity]))
    if seen != set(expected):
        raise ValueError(
            "Tệp duyệt thiếu ID trong mẫu. Xuất toàn bộ để tránh mất phần đã gán trước đó."
        )
    write_jsonl(root / "data/private/samples/manual-review.jsonl", accepted)
    return sum(row["review_status"] == "reviewed" for row in accepted)
