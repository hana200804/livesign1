"""Kiểm đếm YOLO gốc; chưa tạo danh mục lớp hay tập train của LiveSign."""

from __future__ import annotations

import math
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from .io import read_yaml, sha256_file, stable_hash, write_csv, write_json, write_jsonl

LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CDLA-Permissive-2.0"}
SPLITS = {"train": "train", "val": "val", "valid": "val", "test": "test"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def image_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(24)
        if header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR" and len(header) == 24:
            width, height = struct.unpack(">II", header[16:24])
        elif header[:2] == b"\xff\xd8":
            source.seek(2)
            width, height = jpeg_dimensions(source)
        else:
            raise ValueError(f"Định dạng ảnh chưa hỗ trợ hoặc tệp hỏng: {path.name}")
    if width <= 0 or height <= 0:
        raise ValueError("Kích thước ảnh không hợp lệ.")
    return width, height


def jpeg_dimensions(source) -> tuple[int, int]:
    start_of_frames = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while True:
        if source.read(1) != b"\xff":
            raise ValueError("Cấu trúc JPEG không hợp lệ.")
        marker = source.read(1)
        while marker == b"\xff":
            marker = source.read(1)
        if not marker or marker[0] in (0xD9, 0xDA):
            raise ValueError("JPEG không có thông tin kích thước trước dữ liệu ảnh.")
        if marker[0] in (0xD8, 0x01) or 0xD0 <= marker[0] <= 0xD7:
            continue
        packed = source.read(2)
        if len(packed) != 2:
            raise ValueError("JPEG bị cắt ngắn.")
        length = struct.unpack(">H", packed)[0]
        if length < 2:
            raise ValueError("Độ dài marker JPEG không hợp lệ.")
        if marker[0] in start_of_frames:
            dimensions = source.read(5)
            if len(dimensions) != 5:
                raise ValueError("JPEG thiếu kích thước.")
            height, width = struct.unpack(">HH", dimensions[1:5])
            return width, height
        source.seek(length - 2, 1)


def class_names(document: dict) -> list[str]:
    names = document.get("names")
    if isinstance(names, dict):
        try:
            numbered = {int(key): value for key, value in names.items()}
        except (TypeError, ValueError):
            raise ValueError("ID nhãn YOLO phải là số nguyên.") from None
        if set(numbered) != set(range(len(numbered))):
            raise ValueError("ID nhãn YOLO phải liên tiếp từ 0.")
        names = [numbered[index] for index in range(len(numbered))]
    if (
        not isinstance(names, list)
        or not names
        or any(not isinstance(name, str) or not name for name in names)
    ):
        raise ValueError("data.yaml cần names là danh sách nhãn gốc không rỗng.")
    if len(set(names)) != len(names):
        raise ValueError("Tên nhãn gốc bị trùng.")
    if "nc" in document and document["nc"] != len(names):
        raise ValueError("nc khác số phần tử names.")
    return names


def yolo_objects(path: Path, class_count: int) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"Thiếu annotation: {path.name}. Không tự coi là ảnh âm.")
    objects = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5 or not re.fullmatch(r"\d+", parts[0]):
            raise ValueError(
                f"Annotation detect YOLO cần 5 cột, class nguyên: {path.name}:{number}"
            )
        label = int(parts[0])
        try:
            x, y, width, height = map(float, parts[1:])
        except ValueError:
            raise ValueError(f"BBox không phải số: {path.name}:{number}") from None
        if not 0 <= label < class_count or not all(
            math.isfinite(value) for value in (x, y, width, height)
        ):
            raise ValueError(f"ID nhãn hoặc bbox không hợp lệ: {path.name}:{number}")
        if not 0 <= x <= 1 or not 0 <= y <= 1 or not 0 < width <= 1 or not 0 < height <= 1:
            raise ValueError(f"BBox chuẩn hóa ngoài miền: {path.name}:{number}")
        epsilon = 1e-6
        if (
            min(x - width / 2, y - height / 2) < -epsilon
            or max(x + width / 2, y + height / 2) > 1 + epsilon
        ):
            raise ValueError(f"BBox vượt biên ảnh: {path.name}:{number}")
        objects.append({"class_id": label, "xywh": [x, y, width, height]})
    return objects


def discover_images(directory: Path) -> list[tuple[str, Path, Path]]:
    result = []
    resolved = set()
    keys = set()
    for folder_name, split in SPLITS.items():
        for image_root, label_root in (
            (directory / "images" / folder_name, directory / "labels" / folder_name),
            (directory / folder_name / "images", directory / folder_name / "labels"),
        ):
            if not image_root.is_dir():
                continue
            for image in sorted(image_root.rglob("*")):
                if not image.is_file() or image.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                target = image.resolve()
                if not target.is_relative_to(directory.resolve()):
                    raise ValueError("Ảnh trỏ ra ngoài thư mục nguồn.")
                key = image.relative_to(directory).as_posix()
                if target in resolved or key in keys:
                    raise ValueError("Còn khóa ảnh trùng hoặc nhiều đường dẫn trỏ cùng ảnh.")
                resolved.add(target)
                keys.add(key)
                relative = image.relative_to(image_root)
                label = label_root / relative.with_suffix(".txt")
                if not label.resolve().is_relative_to(directory.resolve()):
                    raise ValueError("Annotation trỏ ra ngoài thư mục nguồn.")
                result.append((split, image, label))
    if not result:
        raise ValueError("Không tìm thấy ảnh YOLO trong images/<split> hoặc <split>/images.")
    return result


def validate_source(source: dict) -> None:
    for name in ("id", "url", "version", "license", "license_url"):
        if not source.get(name) or str(source[name]).strip().lower() in (
            "unknown",
            "latest",
            "cần đo",
        ):
            raise ValueError(f"Nguồn cần {name} chính xác, không được Unknown/latest.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", source["id"]):
        raise ValueError("ID nguồn chỉ dùng chữ thường, số, gạch ngang và gạch dưới.")
    if source["license"] not in LICENSES:
        raise ValueError(
            "Giấy phép chưa nằm trong danh sách đã xác định. Cần đối chiếu trước khi dùng dataset."
        )
    if not all(str(source[key]).startswith("https://") for key in ("url", "license_url")):
        raise ValueError("URL nguồn và giấy phép phải là HTTPS.")


def audit_dataset(directory: Path, source: dict, output: Path) -> dict:
    validate_source(source)
    names = class_names(read_yaml(directory / "data.yaml"))
    images = discover_images(directory)
    object_counts = Counter()
    image_counts = Counter()
    sha_groups = defaultdict(list)
    inventory = []
    for split, image, annotation in images:
        width, height = image_dimensions(image)
        objects = yolo_objects(annotation, len(names))
        image_key = f"{source['id']}:{image.relative_to(directory).as_posix()}"
        image_hash = sha256_file(image)
        sha_groups[image_hash].append({"image_key": image_key, "split": split})
        labels_in_image = set()
        for item in objects:
            object_counts[split, item["class_id"]] += 1
            labels_in_image.add(item["class_id"])
        for label in labels_in_image:
            image_counts[split, label] += 1
        inventory.append(
            {
                "image_key": image_key,
                "source": source["id"],
                "original_split": split,
                "image_sha256": image_hash,
                "annotation_sha256": sha256_file(annotation),
                "width_px": width,
                "height_px": height,
                "objects": objects,
            }
        )
    rows = [
        {
            "source": source["id"],
            "version": str(source["version"]),
            "license": source["license"],
            "original_label_id": label,
            "original_label": name,
            "original_split": split,
            "object_count": object_counts[split, label],
            "image_count": image_counts[split, label],
            "qcvn_mapping": "chưa duyệt",
            "crop_review": "cần xem",
        }
        for label, name in enumerate(names)
        for split in ("train", "val", "test")
    ]
    duplicates = [
        {
            "sha256": digest,
            "members": members,
            "cross_split": len({member["split"] for member in members}) > 1,
        }
        for digest, members in sorted(sha_groups.items())
        if len(members) > 1
    ]
    manifest = {
        "source": source,
        "image_count": len(inventory),
        "unique_image_sha256_count": len(sha_groups),
        "object_count": sum(object_counts.values()),
        "inventory_hash": stable_hash(inventory),
        "class_names": names,
        "status": "audited_original_labels_not_approved_for_training",
        "duplicate_group_count": len(duplicates),
        "cross_split_duplicate_group_count": sum(group["cross_split"] for group in duplicates),
        "phash_status": "chưa chạy — Giai đoạn 2",
        "crop_review_status": "cần xem",
    }
    write_csv(output / "label-counts.csv", list(rows[0]), rows)
    write_jsonl(output / "image-inventory.jsonl", inventory)
    write_json(output / "exact-duplicates.json", duplicates)
    write_json(output / "dataset-manifest.json", manifest)
    return manifest
