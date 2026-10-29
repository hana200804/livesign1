"""Gói ảnh CVAT và nhập XML ảnh 1.1, giữ nguyên mẫu khảo sát đã khóa."""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

from .io import read_json, read_jsonl, read_yaml, sha256_file, stable_hash, write_json
from .review import import_review, validate_manual_record

STATES = {"LS_REVIEWED": "reviewed", "LS_EMPTY_CONFIRMED": "reviewed", "LS_UNCLEAR": "unclear"}
MAX_XML_BYTES = 16 * 1024 * 1024


def locked_samples(root: Path) -> tuple[dict, dict[str, dict]]:
    lock = read_json(root / "data/private/samples/sample-lock.json")
    template = read_jsonl(root / "data/private/samples/annotation-template.jsonl")
    expected = {row["image_id"]: row for row in template}
    ids = [row["image_id"] for row in lock["images"]]
    if (
        stable_hash(lock["images"]) != lock["sample_ids_hash"]
        or len(set(ids)) != len(ids)
        or len(expected) != len(template)
        or set(ids) != set(expected)
    ):
        raise ValueError("Mẫu khóa hoặc template đã đổi, thiếu hay trùng ID.")
    return lock, expected


def cvat_labels(root: Path) -> list[dict]:
    codes = [
        row["code"] for row in read_yaml(root / "config/survey-class-candidates.yaml")["classes"]
    ]
    if len(set(codes)) != len(codes):
        raise ValueError("Mã ứng viên trùng; chưa xuất nhãn CVAT.")
    labels = [{"name": code, "type": "rectangle", "attributes": []} for code in codes]
    labels.append(
        {
            "name": "QCVN_OTHER",
            "type": "rectangle",
            "attributes": [
                {
                    "name": "qcvn",
                    "input_type": "text",
                    "mutable": False,
                    "default_value": "",
                    "values": [],
                }
            ],
        }
    )
    labels.extend({"name": name, "type": "tag", "attributes": []} for name in STATES)
    return labels


def export_cvat(root: Path, route: str | None = None, year: int | None = None) -> Path:
    lock, expected = locked_samples(root)
    selected = [
        row
        for row in lock["images"]
        if (route is None or route in row["routes"]) and (year is None or row["year"] == year)
    ]
    if not selected:
        raise ValueError("Bộ lọc tuyến/năm không có ảnh trong mẫu khóa.")
    images = []
    for item in selected:
        identity = item["image_id"]
        if not re.fullmatch(r"[0-9]+", identity):
            raise ValueError("ID ảnh khóa không hợp lệ.")
        row = expected[identity]
        if (
            sha256_file(root / "data/private/samples/images" / f"{identity}.jpg")
            != row["image_sha256"]
        ):
            raise ValueError("Ảnh đã đổi sau khi khóa; chưa đóng gói CVAT.")
        images.append({**item, **row, "file_name": f"{identity}.jpg"})
    labels = cvat_labels(root)
    specification = {"sample_ids_hash": lock["sample_ids_hash"], "images": images, "labels": labels}
    fingerprint = stable_hash(specification)
    # Tên thư mục lấy từ hash, không lấy chuỗi tuyến do CLI truyền vào.
    output = root / "data/private/cvat" / fingerprint[:16]
    manifest_path = output / "manifest.json"
    if output.exists():
        previous = read_json(manifest_path)
        if previous["package_hash"] != fingerprint or set(previous["files"]) != {
            "images.zip",
            "labels.json",
        }:
            raise ValueError("Thư mục gói CVAT khác hash mong đợi.")
        for name, digest in previous["files"].items():
            if name not in ("images.zip", "labels.json") or sha256_file(output / name) != digest:
                raise ValueError("Gói CVAT đã đổi; giữ nguyên để kiểm tra.")
        return output
    output.mkdir(parents=True)
    with zipfile.ZipFile(output / "images.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for item in images:
            archive.write(
                root / "data/private/samples/images" / item["file_name"], item["file_name"]
            )
    write_json(output / "labels.json", labels)
    write_json(
        manifest_path,
        {
            "schema_version": 1,
            "package_hash": fingerprint,
            **specification,
            "files": {name: sha256_file(output / name) for name in ("images.zip", "labels.json")},
            "attribution": "© Mapillary contributors; original images, not AI ground truth",
            "classes_finalized": False,
        },
    )
    (output / "HUONG-DAN.md").write_text(
        "# Gói CVAT khảo sát\n\n"
        f"Có {len(images)} ảnh nguyên bản từ mẫu khóa. © Mapillary contributors.\n\n"
        "Tại app.cvat.ai: tạo task, dán labels.json vào Labels → Raw, upload images.zip.\n"
        "Vẽ rectangle đúng mã; mã khác dùng QCVN_OTHER và điền thuộc tính qcvn.\n"
        "Mỗi ảnh xem xong gắn đúng MỘT tag: LS_REVIEWED (có bbox), "
        "LS_EMPTY_CONFIRMED (đã xem toàn ảnh, không có biển), LS_UNCLEAR (chưa chắc).\n"
        "Không có tag thì vẫn pending, kể cả đã vẽ box. Không chạy auto annotation cho GT này.\n"
        "Save, Export annotations → CVAT for images 1.1; không cần xuất kèm ảnh.\n"
        "Gửi đường dẫn XML/ZIP tải xuống; giữ manifest.json để kiểm ID/hash.\n"
        "Danh mục mã hiện chỉ là ứng viên, chưa chốt lớp train.\n",
        encoding="utf-8",
        newline="\n",
    )
    return output


def annotation_xml(path: Path) -> ET.Element:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            entries = [
                item
                for item in archive.infolist()
                if PurePosixPath(item.filename).name == "annotations.xml"
            ]
            if len(entries) != 1 or entries[0].file_size > MAX_XML_BYTES:
                raise ValueError("ZIP cần đúng một annotations.xml, tối đa 16 MiB.")
            data = archive.read(entries[0])
    else:
        if path.stat().st_size > MAX_XML_BYTES:
            raise ValueError("XML vượt 16 MiB.")
        data = path.read_bytes()
    text = data.decode("utf-8-sig")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Không nhận DTD/entity trong XML CVAT.")
    try:
        document = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("XML CVAT không hợp lệ.") from error
    if (
        document.tag != "annotations"
        or document.findtext("version") != "1.1"
        or document.find("track") is not None
    ):
        raise ValueError("Cần CVAT for images 1.1; không nhận video/track.")
    if any(
        (node.text or "").strip().lower() not in ("false", "0", "")
        for node in document.findall("meta/task/flipped")
    ):
        raise ValueError("Không nhận task lật ảnh: bbox không còn cùng hệ tọa độ ảnh khóa.")
    return document


def cvat_record(image: ET.Element, expected: dict, label_names: set[str]) -> dict:
    if (int(image.get("width", "0")), int(image.get("height", "0"))) != (
        expected["width_px"],
        expected["height_px"],
    ):
        raise ValueError("Kích thước ảnh CVAT khác mẫu khóa.")
    tags = image.findall("tag")
    if len(tags) > 1 or any(tag.get("label") not in STATES for tag in tags):
        raise ValueError("Mỗi ảnh cần tối đa một tag trạng thái LiveSign.")
    state = tags[0].get("label") if tags else None
    boxes = []
    for shape in image:
        if shape.tag == "tag":
            if shape.get("source", "manual") != "manual":
                raise ValueError("Tag trạng thái phải do người duyệt xác nhận.")
            continue
        if shape.tag != "box" or float(shape.get("rotation", "0")) != 0:
            raise ValueError("Chỉ nhận rectangle không xoay; không bỏ qua shape khác.")
        if shape.get("source", "manual") != "manual":
            raise ValueError("Không nhận bbox auto thành ground truth độc lập.")
        label = shape.get("label", "")
        if label not in label_names:
            raise ValueError("Nhãn CVAT không thuộc gói đã xuất.")
        if label == "QCVN_OTHER":
            values = shape.findall("attribute[@name='qcvn']")
            if len(values) != 1:
                raise ValueError("QCVN_OTHER cần đúng một thuộc tính qcvn.")
            label = (values[0].text or "").strip()
        boxes.append(
            {
                "label": label,
                "bbox_xyxy": [float(shape.get(key, "nan")) for key in ("xtl", "ytl", "xbr", "ybr")],
            }
        )
    row = {
        **expected,
        "boxes": boxes,
        "label_source": "manual",
        "review_status": STATES[state] if state else "pending",
        "explicit_empty": state == "LS_EMPTY_CONFIRMED",
    }
    if state == "LS_REVIEWED" and not boxes:
        raise ValueError("Ảnh không có bbox cần tag LS_EMPTY_CONFIRMED hoặc LS_UNCLEAR.")
    return validate_manual_record(row, expected)


def import_cvat(root: Path, path: Path, package: Path) -> int:
    lock, expected = locked_samples(root)
    manifest = read_json(package / "manifest.json")
    specification = {key: manifest[key] for key in ("sample_ids_hash", "images", "labels")}
    if (
        stable_hash(specification) != manifest["package_hash"]
        or manifest["sample_ids_hash"] != lock["sample_ids_hash"]
    ):
        raise ValueError("Gói CVAT không còn khớp mẫu khóa.")
    package_images = {row["file_name"]: row for row in manifest["images"]}
    if len(package_images) != len(manifest["images"]):
        raise ValueError("Gói CVAT có tên ảnh trùng.")
    for row in package_images.values():
        if row["image_id"] not in expected or any(
            row[key] != expected[row["image_id"]][key]
            for key in ("image_sha256", "width_px", "height_px")
        ):
            raise ValueError("Metadata ảnh gói CVAT khác template khóa.")
    label_names = {row["name"] for row in manifest["labels"] if row["type"] == "rectangle"}
    document = annotation_xml(path)
    converted = {}
    visited = set()
    for image in document.findall("image"):
        name = PurePosixPath(image.get("name", "").replace("\\", "/"))
        if (
            name.is_absolute()
            or ".." in name.parts
            or name.name not in package_images
            or name.name in visited
        ):
            raise ValueError("Tên ảnh CVAT lạ, trùng hoặc chứa đường dẫn không hợp lệ.")
        visited.add(name.name)
        identity = package_images[name.name]["image_id"]
        converted[identity] = cvat_record(image, expected[identity], label_names)
    if visited != set(package_images):
        raise ValueError("CVAT export thiếu ảnh của gói; cần xuất toàn task.")
    # Task có thể chỉ chứa 12/108 ảnh. Giữ kết quả đã nhập từ các đợt trước.
    canonical = root / "data/private/samples/manual-review.jsonl"
    merged = {}
    if canonical.exists():
        for row in read_jsonl(canonical):
            identity = row["image_id"]
            if identity not in expected or identity in merged:
                raise ValueError("Nhãn đã nhập có ID lạ hoặc trùng.")
            merged[identity] = validate_manual_record(row, expected[identity])
    for identity, row in converted.items():
        if row["review_status"] != "pending" or identity not in merged:
            merged[identity] = row
    normalized = root / "data/private/cvat/imports" / f"{sha256_file(path)}.json"
    write_json(
        normalized,
        {
            "sample_ids_hash": lock["sample_ids_hash"],
            "annotation_origin": "human_review_ui",
            "images": [
                merged.get(identity, {"image_id": identity, "review_status": "pending"})
                for identity in expected
            ],
            "source": {
                "format": "CVAT for images 1.1",
                "sha256": sha256_file(path),
                "package_hash": manifest["package_hash"],
            },
        },
    )
    if canonical.exists():
        backup = root / "data/private/cvat/imports" / f"previous-{sha256_file(canonical)}.jsonl"
        if not backup.exists():
            shutil.copyfile(canonical, backup)
    return import_review(root, normalized)
