import ast
import copy
from pathlib import Path

import pytest

from survey.io import read_yaml
from survey.poc import iou, nms_by_class, restore_box, validate_image_hash
from survey.review import validate_manual_record

ROOT = Path(__file__).resolve().parent.parent


def manual():
    return {
        "image_id": "image",
        "image_sha256": "locked",
        "width_px": 1280,
        "height_px": 720,
        "review_status": "reviewed",
        "explicit_empty": False,
        "label_source": "manual",
        "boxes": [{"label": "P.102", "bbox_xyxy": [512, 296, 768, 424]}],
    }


def test_letterbox_inverse_matches_contract_example():
    assert restore_box([320, 320, 128, 64], 1280, 720) == [512, 296, 768, 424]


def test_changed_image_cannot_use_old_sample_manifest(tmp_path):
    from survey.io import sha256_file
    from survey.network import SurveyError

    image = tmp_path / "image.jpg"
    image.write_bytes(b"original fixture bytes")
    expected = sha256_file(image)
    assert validate_image_hash(image, expected) == expected
    image.write_bytes(b"changed fixture bytes")
    with pytest.raises(SurveyError, match="đã đổi"):
        validate_image_hash(image, expected)


def test_nms_preserves_different_classes_on_same_box():
    first = {"class_id": 0, "confidence": 0.9, "bbox_xyxy": [10, 10, 50, 50]}
    duplicate = {**first, "confidence": 0.5}
    other_class = {**first, "class_id": 1}
    assert nms_by_class([duplicate, other_class, first], 0.45) == [first, other_class]
    assert iou(first["bbox_xyxy"], first["bbox_xyxy"]) == 1


def test_manual_bboxes_retain_image_provenance():
    row = manual()
    accepted = validate_manual_record(row, row)
    assert accepted["boxes"] == row["boxes"]
    assert accepted["image_sha256"] == "locked"


def test_empty_review_requires_deliberate_confirmation():
    expected = manual()
    row = {**expected, "boxes": []}
    with pytest.raises(ValueError, match="xác nhận rỗng"):
        validate_manual_record(row, expected)
    assert (
        validate_manual_record({**row, "explicit_empty": True}, expected)["review_status"]
        == "reviewed"
    )


@pytest.mark.parametrize(
    "box", [[-1, 0, 20, 20], [1, 2, 1, 3], [0, 0, 1281, 20], [0, float("nan"), 10, 10]]
)
def test_invalid_manual_bboxes_cannot_become_ground_truth(box):
    expected = manual()
    row = copy.deepcopy(expected)
    row["boxes"][0]["bbox_xyxy"] = box
    with pytest.raises(ValueError):
        validate_manual_record(row, expected)


def test_ai_label_source_cannot_become_manual_ground_truth():
    expected = manual()
    with pytest.raises(ValueError, match="nguồn gán tay"):
        validate_manual_record({**expected, "label_source": "mapillary_ai"}, expected)


def test_pure_modules_have_no_top_level_heavy_dependencies():
    prohibited = {"numpy", "torch", "PIL", "ultralytics", "onnxruntime", "tensorflow"}
    for path in (ROOT / "survey").glob("*.py"):
        document = ast.parse(path.read_text(encoding="utf-8"))
        for node in document.body:
            imported = (
                [alias.name.split(".")[0] for alias in node.names]
                if isinstance(node, ast.Import)
                else [(node.module or "").split(".")[0]]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not prohibited.intersection(imported), path.name


def test_all_thresholds_have_status_and_negative_evidence_stays_off():
    parameters = read_yaml(ROOT / "config/params.yaml")
    assert all(row["status"] in ("đã chốt", "dự kiến") for row in parameters.values())
    assert parameters["negative_evidence_enabled"]["value"] is False
