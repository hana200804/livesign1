"""PoC detector ONNX có sẵn. Không train và không tự tạo ground truth."""

from __future__ import annotations

import ast
import statistics
import time
from collections import Counter
from pathlib import Path

from .io import (
    implementation_manifest,
    read_json,
    read_jsonl,
    sha256_file,
    stable_hash,
    write_csv,
    write_json,
    write_jsonl,
)
from .network import Http, SurveyError, canonical_id

MODEL_REVISION = "550d5844685059befd78909414baa33202700c87"
MODEL_SHA256 = "08586b55e8761ba257035a4c1fcd12aeec5ae5206eb737f4fe16029e64c01854"


def prepare_poc(root: Path) -> None:
    output = root / "data/private/poc-model"
    base = f"https://huggingface.co/liamxdev/vtsr/resolve/{MODEL_REVISION}/"
    for name in ("vtsr_int8.onnx", "label-mapping.json"):
        if not (output / name).exists():
            Http(timeout_s=120).download(base + name, output / name)
    if sha256_file(output / "vtsr_int8.onnx") != MODEL_SHA256:
        raise SurveyError("Hash detector PoC không khớp revision chính thức.")
    print("Detector PoC đã sẵn sàng, đã kiểm SHA-256. Chưa train model LiveSign.")


def validate_image_hash(path: Path, expected: str | None) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise SurveyError("Ảnh PoC đã đổi hoặc thiếu trong manifest khóa hash. Dừng suy luận.")
    return actual


def restore_box(xywh: list[float], width: int, height: int, input_size: int = 640) -> list[float]:
    gain = min(input_size / width, input_size / height)
    left = (input_size - round(width * gain)) // 2
    top = (input_size - round(height * gain)) // 2
    cx, cy, box_width, box_height = xywh
    return [
        max(0, min(width, (cx - box_width / 2 - left) / gain)),
        max(0, min(height, (cy - box_height / 2 - top) / gain)),
        max(0, min(width, (cx + box_width / 2 - left) / gain)),
        max(0, min(height, (cy + box_height / 2 - top) / gain)),
    ]


def iou(first: list[float], second: list[float]) -> float:
    intersection = max(0, min(first[2], second[2]) - max(first[0], second[0]))
    intersection *= max(0, min(first[3], second[3]) - max(first[1], second[1]))
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def nms_by_class(candidates: list[dict], threshold: float) -> list[dict]:
    kept = []
    for candidate in sorted(
        candidates, key=lambda row: (-row["confidence"], row["class_id"], row["bbox_xyxy"])
    ):
        if any(
            candidate["class_id"] == previous["class_id"]
            and iou(candidate["bbox_xyxy"], previous["bbox_xyxy"]) > threshold
            for previous in kept
        ):
            continue
        kept.append(candidate)
    return kept


def run_poc(root: Path, params: dict) -> None:
    # Import tùy chọn chỉ khi chạy PoC. CI thuần không cần NumPy, Pillow hay ONNX Runtime.
    import numpy as np
    import onnxruntime as ort
    from PIL import Image, ImageDraw

    model = root / "data/private/poc-model/vtsr_int8.onnx"
    if sha256_file(model) != MODEL_SHA256:
        raise SurveyError("Hash detector PoC khác revision đã kiểm. Dừng suy luận.")
    lock = read_json(root / "data/private/samples/sample-lock.json")
    if stable_hash(lock["images"]) != lock["sample_ids_hash"]:
        raise SurveyError("Danh sách ảnh mẫu đã đổi sau khi khóa.")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
    if (
        session.get_inputs()[0].shape != [1, 3, 640, 640]
        or session.get_inputs()[0].type != "tensor(float)"
    ):
        raise SurveyError("Tensor đầu vào detector PoC khác hợp đồng bộ giải mã.")
    shape = session.get_outputs()[0].shape
    names = ast.literal_eval(session.get_modelmeta().custom_metadata_map["names"])
    if (
        not isinstance(names, dict)
        or set(names) != set(range(len(names)))
        or shape != [1, 4 + len(names), 8400]
    ):
        raise SurveyError("Tensor hoặc thứ tự nhãn detector PoC không phù hợp.")
    confidence = params["poc_confidence_threshold"]["value"]
    nms_threshold = params["poc_nms_iou_threshold"]["value"]
    predictions, frame_rows = [], []
    output = root / "data/private/poc"
    sizes = []
    expected_hashes = {
        row["image_id"]: row["image_sha256"]
        for row in read_jsonl(root / "data/private/samples/annotation-template.jsonl")
    }
    for item in lock["images"]:
        canonical_id(item["image_id"])
        image_path = root / "data/private/samples/images" / f"{item['image_id']}.jpg"
        validate_image_hash(image_path, expected_hashes.get(item["image_id"]))
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
        width, height = image.size
        gain = min(640 / width, 640 / height)
        resized_width, resized_height = round(width * gain), round(height * gain)
        canvas = Image.new("RGB", (640, 640), (114, 114, 114))
        canvas.paste(
            image.resize((resized_width, resized_height), Image.Resampling.BILINEAR),
            ((640 - resized_width) // 2, (640 - resized_height) // 2),
        )
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        started = time.perf_counter()
        raw = session.run(None, {session.get_inputs()[0].name: tensor})[0][0].T
        inference_ms = (time.perf_counter() - started) * 1000
        class_ids = np.argmax(raw[:, 4:], axis=1)
        scores = np.max(raw[:, 4:], axis=1)
        candidates = []
        for index in np.flatnonzero(scores >= confidence):
            box = restore_box(raw[index, :4].tolist(), width, height)
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            candidates.append(
                {
                    "class_id": int(class_ids[index]),
                    "label": names[int(class_ids[index])],
                    "confidence": float(scores[index]),
                    "bbox_xyxy": box,
                }
            )
        boxes = nms_by_class(candidates, nms_threshold)
        predictions.append(
            {
                "image_id": item["image_id"],
                "year": item["year"],
                "image_sha256": sha256_file(image_path),
                "boxes": boxes,
            }
        )
        frame_rows.append(
            {
                "image_id": item["image_id"],
                "year": item["year"],
                "routes": ";".join(item["routes"]),
                "width_px": width,
                "height_px": height,
                "predicted_box_count": len(boxes),
                "inference_ms": round(inference_ms, 3),
                "ground_truth_status": "not_annotated",
            }
        )
        draw = ImageDraw.Draw(image)
        for box in boxes:
            draw.rectangle(box["bbox_xyxy"], outline="#e52c42", width=max(2, width // 700))
            draw.text(
                (box["bbox_xyxy"][0], max(0, box["bbox_xyxy"][1] - 12)),
                f"{box['label']} {box['confidence']:.2f}",
                fill="#e52c42",
            )
            sizes.append(
                min(
                    box["bbox_xyxy"][2] - box["bbox_xyxy"][0],
                    box["bbox_xyxy"][3] - box["bbox_xyxy"][1],
                )
            )
        (output / "previews").mkdir(parents=True, exist_ok=True)
        image.thumbnail((1280, 1280))
        image.save(output / "previews" / f"{item['image_id']}.jpg", quality=88)
    write_jsonl(output / "predictions.jsonl", predictions)
    report = root / "reports/stage0"
    write_csv(report / "poc-frames.csv", list(frame_rows[0]), frame_rows)
    totals = Counter(box["label"] for prediction in predictions for box in prediction["boxes"])
    write_json(
        report / "poc-manifest.json",
        {
            "model_source": "https://huggingface.co/liamxdev/vtsr",
            "revision": MODEL_REVISION,
            "model_sha256": MODEL_SHA256,
            "license": "AGPL-3.0",
            "purpose": "pretrained_detector_poc_only",
            **implementation_manifest(),
            "sample_ids_hash": lock["sample_ids_hash"],
            "python_packages": {"numpy": np.__version__, "onnxruntime": ort.__version__},
            "input_tensor": session.get_inputs()[0].shape,
            "output_tensor": shape,
            "confidence_threshold": confidence,
            "nms_iou_threshold": nms_threshold,
            "frame_count": len(frame_rows),
            "frames_with_detections": sum(bool(row["predicted_box_count"]) for row in frame_rows),
            "predicted_box_count_by_original_label": dict(totals),
            "predicted_min_side_median_px": statistics.median(sizes) if sizes else None,
            "raw_recall": None,
            "raw_recall_status": "needs_independent_manual_boxes",
            "negative_evidence_enabled": False,
            "params_hash": stable_hash(params),
        },
    )
    sample_manifest = read_json(report / "sample-manifest.json")
    sample_manifest["detector_status"] = "completed_pretrained_poc"
    sample_manifest["predictions_sha256"] = sha256_file(output / "predictions.jsonl")
    write_json(report / "sample-manifest.json", sample_manifest)
    print(f"PoC đã chạy trên {len(frame_rows)} ảnh. Recall cần bbox gán tay độc lập.")
