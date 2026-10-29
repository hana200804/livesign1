"""Chấm PoC bằng bbox gán tay. Không đưa nhãn AI vào ground truth hay bật B3."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .io import (
    implementation_manifest,
    read_json,
    read_jsonl,
    read_yaml,
    sha256_file,
    stable_hash,
    write_csv,
    write_json,
)
from .network import canonical_id
from .poc import iou
from .review import validate_manual_record


def checked_box(box: dict, width: int, height: int, prediction: bool) -> None:
    if not isinstance(box, dict) or not isinstance(box.get("label"), str) or not box["label"]:
        raise ValueError("BBox cần nhãn chuỗi không rỗng.")
    coordinates = box.get("bbox_xyxy")
    if (
        not isinstance(coordinates, list)
        or len(coordinates) != 4
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in coordinates
        )
    ):
        raise ValueError("BBox cần bốn tọa độ px hữu hạn.")
    left, top, right, bottom = coordinates
    if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
        raise ValueError("BBox nằm ngoài ảnh hoặc không có diện tích.")
    if prediction:
        confidence = box.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Confidence của dự đoán phải nằm trong [0,1].")


def match_boxes(truth: list[dict], predictions: list[dict], threshold: float) -> list[dict]:
    """Khớp một–một nhiều nhất theo cùng nhãn và IoU; không phải AP/mAP chuẩn COCO."""
    if not 0 < threshold <= 1:
        raise ValueError("Ngưỡng IoU cần >0 và ≤1.")
    neighbors = {
        index: sorted(
            [
                (other, iou(box["bbox_xyxy"], candidate["bbox_xyxy"]))
                for other, candidate in enumerate(predictions)
                if box["label"] == candidate["label"]
                and iou(box["bbox_xyxy"], candidate["bbox_xyxy"]) >= threshold
            ],
            key=lambda pair: (-pair[1], pair[0]),
        )
        for index, box in enumerate(truth)
    }
    owners: dict[int, int] = {}

    def augment(truth_index: int, visited: set[int]) -> bool:
        for prediction_index, _ in neighbors[truth_index]:
            if prediction_index in visited:
                continue
            visited.add(prediction_index)
            if prediction_index not in owners or augment(owners[prediction_index], visited):
                owners[prediction_index] = truth_index
                return True
        return False

    for index in range(len(truth)):
        augment(index, set())
    return [
        {
            "truth_index": truth_index,
            "prediction_index": prediction_index,
            "iou": iou(truth[truth_index]["bbox_xyxy"], predictions[prediction_index]["bbox_xyxy"]),
        }
        for prediction_index, truth_index in sorted(owners.items(), key=lambda pair: pair[1])
    ]


def reviewed_mapping(decisions: list[dict], original_labels: set[str]) -> dict[str, str | None]:
    mapping = {}
    for item in decisions:
        label = item.get("original_label")
        if label not in original_labels or label in mapping:
            raise ValueError("Ánh xạ PoC có nhãn nguồn lạ hoặc trùng.")
        if item.get("review_status") != "human_confirmed" or not item.get("evidence_note"):
            raise ValueError("Ánh xạ chấm điểm cần xác nhận người duyệt và ghi chú bằng chứng.")
        action = item.get("action")
        if action == "map":
            code = item.get("qcvn")
            if not isinstance(code, str) or not re.fullmatch(
                r"(?:DP|P|W|I|R|S)\.\d{3}[a-z]?", code
            ):
                raise ValueError("Mã QCVN trong ánh xạ PoC không hợp lệ.")
            mapping[label] = code
        elif action == "exclude":
            mapping[label] = None
        else:
            raise ValueError("Nhãn lẫn chưa được phép map hay exclude tự động.")
    if set(mapping) != original_labels:
        raise ValueError("Chưa có quyết định duyệt cho toàn bộ nhãn đầu ra detector.")
    if not any(value is not None for value in mapping.values()):
        raise ValueError("Phạm vi chấm cần ít nhất một mã QCVN đã xác nhận.")
    return mapping


def size_bucket(box: list[float], small_px: int, medium_px: int) -> str:
    short = min(box[2] - box[0], box[3] - box[1])
    return "small" if short < small_px else "medium" if short < medium_px else "large"


def score_records(
    truth_rows: list[dict],
    predictions: list[dict],
    mapping: dict[str, str | None],
    years: dict[str, int],
    threshold: float,
    small_px: int,
    medium_px: int,
) -> tuple[list[dict], list[dict]]:
    if not 0 < small_px < medium_px:
        raise ValueError("Mốc cỡ bbox phải tăng dần và >0 px.")
    predicted = {row["image_id"]: row for row in predictions}
    if len(predicted) != len(predictions):
        raise ValueError("Dự đoán có ID ảnh trùng.")
    scope = {value for value in mapping.values() if value is not None}
    tallies = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "images": set()})
    matches = []
    seen_ids = set()
    for row in truth_rows:
        identity = row["image_id"]
        if identity in seen_ids:
            raise ValueError("Ground truth có ID ảnh trùng.")
        seen_ids.add(identity)
        if row["review_status"] != "reviewed" or row.get("label_source") != "manual":
            raise ValueError("Chỉ chấm bbox gán tay đã duyệt, không chấm ảnh chưa rõ.")
        if identity not in predicted or identity not in years:
            raise ValueError("Ảnh gán tay thiếu dự đoán hoặc thiếu năm từ mẫu đã khóa.")
        prediction = predicted[identity]
        if prediction.get("image_sha256") != row["image_sha256"]:
            raise ValueError("Ảnh dự đoán khác hash ground truth.")
        width, height = row["width_px"], row["height_px"]
        for box in row["boxes"]:
            checked_box(box, width, height, prediction=False)
        candidates = []
        for box in prediction["boxes"]:
            checked_box(box, width, height, prediction=True)
            if box["label"] not in mapping:
                raise ValueError("Dự đoán có nhãn chưa được người duyệt quyết định ánh xạ.")
            if mapping[box["label"]] is not None:
                candidates.append({**box, "label": mapping[box["label"]]})
        truth = [box for box in row["boxes"] if box["label"] in scope]
        pairs = match_boxes(truth, candidates, threshold)
        true_indices = {pair["truth_index"] for pair in pairs}
        predicted_indices = {pair["prediction_index"] for pair in pairs}
        for group in (("all", "all"), ("year", str(years[identity]))):
            tallies[group]["tp"] += len(pairs)
            tallies[group]["fp"] += len(candidates) - len(pairs)
            tallies[group]["fn"] += len(truth) - len(pairs)
            tallies[group]["images"].add(identity)
        for index, box in enumerate(truth):
            for group in (
                ("class", box["label"]),
                ("bbox_short_side_px", size_bucket(box["bbox_xyxy"], small_px, medium_px)),
            ):
                tallies[group]["tp" if index in true_indices else "fn"] += 1
                tallies[group]["images"].add(identity)
        for index, box in enumerate(candidates):
            if index not in predicted_indices:
                tallies["class", box["label"]]["fp"] += 1
                tallies["class", box["label"]]["images"].add(identity)
        for pair in pairs:
            matches.append({"image_id": identity, "year": years[identity], **pair})
    rows = []
    for (slice_type, value), tally in sorted(tallies.items()):
        tp, fp, fn = tally["tp"], tally["fp"], tally["fn"]
        rows.append(
            {
                "slice_type": slice_type,
                "slice": value,
                "image_count": len(tally["images"]),
                "true_positive": tp,
                "false_positive": fp if slice_type != "bbox_short_side_px" else None,
                "false_negative": fn,
                "precision": tp / (tp + fp)
                if tp + fp and slice_type != "bbox_short_side_px"
                else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "iou_threshold": threshold,
                "method": "maximum_cardinality_same_class_iou",
            }
        )
    return rows, matches


def evaluate_poc(root: Path) -> dict:
    report = root / "reports/stage0"
    manual_path = root / "data/private/samples/manual-review.jsonl"
    output = report / "poc-evaluation.json"
    result = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "not_run",
        "recall": None,
        "purpose": "stage0_pretrained_poc_not_final_model_metrics_or_b3",
        "negative_evidence_enabled": False,
        "reasons": [],
        "metrics_valid": False,
        "outputs": [],
        **implementation_manifest(),
    }
    write_json(
        output,
        {
            **result,
            "reasons": [
                "Kiểm tra đầu vào chưa hoàn tất. Nếu lệnh lỗi thì CSV cũ không còn hiệu lực."
            ],
        },
    )
    manual = []
    mapping: dict[str, str | None] = {}
    if not manual_path.exists():
        result["reasons"].append("Chưa có bbox gán tay do người duyệt xuất và nhập vào hệ thống.")
    else:
        manual = read_jsonl(manual_path)
        if not any(row.get("review_status") == "reviewed" for row in manual):
            result["reasons"].append("Chưa có ảnh gán tay nào ở trạng thái đã duyệt.")
    configuration_path = root / "config/survey-class-candidates.yaml"
    configuration = read_yaml(configuration_path)
    poc_path = report / "poc-manifest.json"
    poc = read_json(poc_path)
    output_labels = poc.get("output_labels", [])
    if not output_labels or len(set(output_labels)) != len(output_labels):
        result["reasons"].append("PoC thiếu danh sách nhãn đầu ra thật, cần chạy lại poc.")
    source_classes = set(output_labels)
    try:
        mapping = reviewed_mapping(configuration["poc_mapping_decisions"], source_classes)
    except ValueError as error:
        result["reasons"].append(str(error))
    if result["reasons"]:
        # Chỉ manifest này quyết định trạng thái. Không xuất CSV metrics có số giả khi thiếu nhãn.
        write_json(output, result)
        return result
    lock_path = root / "data/private/samples/sample-lock.json"
    lock = read_json(lock_path)
    if stable_hash(lock["images"]) != lock["sample_ids_hash"]:
        raise ValueError("Danh sách mẫu đã đổi sau khi khóa.")
    prediction_path = root / "data/private/poc/predictions.jsonl"
    sample_path = report / "sample-manifest.json"
    sample = read_json(sample_path)
    if (
        poc["sample_ids_hash"] != lock["sample_ids_hash"]
        or sample["sample_ids_hash"] != lock["sample_ids_hash"]
        or sample.get("predictions_sha256") != sha256_file(prediction_path)
    ):
        raise ValueError("Hash dự đoán hoặc mẫu không khớp lần PoC đã chạy.")
    expected_path = root / "data/private/samples/annotation-template.jsonl"
    template = read_jsonl(expected_path)
    expected = {row["image_id"]: row for row in template}
    years = {row["image_id"]: row["year"] for row in lock["images"]}
    if (
        len(expected) != len(template)
        or len(years) != len(lock["images"])
        or set(expected) != set(years)
    ):
        raise ValueError("Template annotation không đủ ID trong mẫu khóa.")
    checked = []
    visited = set()
    for row in manual:
        identity = row["image_id"]
        canonical_id(identity)
        if identity not in expected or identity in visited:
            raise ValueError("Ground truth có ID ngoài mẫu hoặc trùng ID.")
        visited.add(identity)
        validate_manual_record(row, expected[identity])
        if (
            sha256_file(root / "data/private/samples/images" / f"{identity}.jpg")
            != row["image_sha256"]
        ):
            raise ValueError("Ảnh gán tay đã đổi sau khi khóa hash.")
        if row["review_status"] == "reviewed":
            checked.append(row)
    params_path = root / "config/params.yaml"
    params = read_yaml(params_path)
    predictions = read_jsonl(prediction_path)
    prediction_ids = [row["image_id"] for row in predictions]
    if len(set(prediction_ids)) != len(prediction_ids) or set(prediction_ids) != set(years):
        raise ValueError("Danh sách dự đoán thiếu, trùng hoặc có ID ngoài mẫu đã khóa.")
    if any(row.get("year") != years[row["image_id"]] for row in predictions):
        raise ValueError("Năm dự đoán khác năm ảnh trong mẫu đã khóa.")
    metrics, matches = score_records(
        checked,
        predictions,
        mapping,
        years,
        params["poc_iou_threshold"]["value"],
        params["poc_small_bbox_px"]["value"],
        params["poc_medium_bbox_px"]["value"],
    )
    metrics_path, matches_path = (
        report / "poc-review-metrics.csv",
        report / "poc-review-matches.csv",
    )
    write_csv(metrics_path, list(metrics[0]), metrics)
    write_csv(matches_path, ["image_id", "year", "truth_index", "prediction_index", "iou"], matches)
    overall = next(row for row in metrics if row["slice_type"] == "all")
    result.update(
        {
            "status": "reviewed_subset" if len(checked) < len(years) else "all_images_reviewed",
            "recall": overall["recall"],
            "metrics_valid": True,
            "reviewed_images": len(checked),
            "locked_images": len(years),
            "scope_qcvn": sorted({value for value in mapping.values() if value is not None}),
            "out_of_scope_manual_boxes": sum(
                box["label"] not in mapping.values() for row in checked for box in row["boxes"]
            ),
            "inputs": [
                {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
                for path in (
                    manual_path,
                    configuration_path,
                    lock_path,
                    expected_path,
                    prediction_path,
                    poc_path,
                    sample_path,
                    params_path,
                )
            ],
            "outputs": [
                {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
                for path in (metrics_path, matches_path)
            ],
            "limitations": [
                "Kết quả là PoC theo lớp đã duyệt; không phải mAP hay bài thử B3.",
                "Không dùng tập con đã duyệt để suy toàn bộ mẫu khi còn ảnh chưa rõ.",
            ],
        }
    )
    write_json(output, result)
    return result
