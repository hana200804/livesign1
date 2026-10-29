from copy import deepcopy

import pytest

from survey.candidates import build_matrix, summarize_routes
from survey.evaluation import (
    checked_box,
    evaluate_poc,
    match_boxes,
    reviewed_mapping,
    score_records,
    size_bucket,
)
from survey.io import read_json, sha256_file, stable_hash, write_json, write_jsonl


def box(label="P.102", coordinates=None, confidence=0.9):
    return {"label": label, "bbox_xyxy": coordinates or [0, 0, 20, 20], "confidence": confidence}


def review():
    return {
        "image_id": "123",
        "image_sha256": "same",
        "width_px": 100,
        "height_px": 100,
        "review_status": "reviewed",
        "label_source": "manual",
        "boxes": [box()],
        "explicit_empty": False,
    }


def decisions():
    return [
        {
            "original_label": "P-102",
            "action": "map",
            "qcvn": "P.102",
            "review_status": "human_confirmed",
            "evidence_note": "synthetic fixture only",
        },
        {
            "original_label": "other",
            "action": "exclude",
            "review_status": "human_confirmed",
            "evidence_note": "fixture outside selected scope",
        },
    ]


def test_candidate_matrix_keeps_zero_year_and_never_calls_hints_verified():
    classes = [
        {
            "code": "P.102",
            "original_labels": ["P-102"],
            "hints": ["hint"],
            "mapping_review": "pending",
        }
    ]
    routes = [{"route": "r", "length_m": 1500}]
    labels = [{"original_label": "P-102", "original_split": "train", "object_count": 23}]
    hints = [
        {
            "route": "r",
            "year": 2023,
            "hint_label": "hint",
            "feature_hint_count": 7,
            "hints_with_passing_images": 6,
            "hints_with_ge2_passing_creators": 2,
        }
    ]
    matrix = build_matrix(classes, routes, [2023, 2024, 2025], labels, hints)
    assert [row["hints_with_passing_images"] for row in matrix] == [6, 0, 0]
    assert all(row["confirmed_route_objects"] is None for row in matrix)
    assert all(row["confirmed_train_objects"] is None for row in matrix)
    assert matrix[0]["raw_train_objects"] == 23
    assert summarize_routes(matrix, routes, [2023, 2024, 2025])[0]["candidate_codes"] == ""


def test_missing_candidate_year_cannot_be_counted_as_complete():
    with pytest.raises(ValueError, match="thiếu một năm"):
        summarize_routes(
            [{"route": "r", "candidate_qcvn": "P.102", "year": 2023}],
            [{"route": "r", "length_m": 1500}],
            [2023, 2024, 2025],
        )


def test_duplicate_label_split_counts_are_rejected_before_aggregation():
    label = {"original_label": "P-102", "original_split": "train", "object_count": 1}
    with pytest.raises(ValueError, match="bị trùng"):
        build_matrix([], [{"route": "r"}], [2023], [label, label], [])


def test_maximum_matching_recovers_pair_lost_by_greedy_iou():
    # A có thể khớp X/Y; B chỉ khớp X. Greedy A→X sẽ bỏ B.
    truth = [box(coordinates=[0, 0, 10, 10]), box(coordinates=[4, 0, 14, 10])]
    predicted = [box(coordinates=[1, 0, 11, 10]), box(coordinates=[-2, 0, 8, 10])]
    pairs = match_boxes(truth, predicted, 0.5)
    assert {(row["truth_index"], row["prediction_index"]) for row in pairs} == {(0, 1), (1, 0)}


def test_match_requires_same_class_and_includes_exact_iou_boundary():
    assert match_boxes([box()], [box(label="P.130")], 0.5) == []
    assert len(match_boxes([box()], [box(coordinates=[0, 0, 10, 20])], 0.5)) == 1


def test_duplicate_detections_become_false_positives_not_extra_recall():
    truth = review()
    prediction = {"image_id": "123", "image_sha256": "same", "boxes": [box(label="P-102")] * 2}
    rows, matches = score_records(
        [truth], [prediction], {"P-102": "P.102"}, {"123": 2023}, 0.5, 32, 96
    )
    overall = next(row for row in rows if row["slice_type"] == "all")
    assert (overall["true_positive"], overall["false_positive"], overall["false_negative"]) == (
        1,
        1,
        0,
    )
    assert overall["precision"] == 0.5 and overall["recall"] == 1
    assert len(matches) == 1


def test_empty_reviewed_frame_counts_false_positive_with_undefined_recall():
    truth = {**review(), "boxes": [], "explicit_empty": True}
    predicted = {"image_id": "123", "image_sha256": "same", "boxes": [box(label="P-102")]}
    rows, _ = score_records([truth], [predicted], {"P-102": "P.102"}, {"123": 2023}, 0.5, 32, 96)
    overall = next(row for row in rows if row["slice_type"] == "all")
    assert overall["false_positive"] == 1 and overall["recall"] is None


@pytest.mark.parametrize("status", ["pending", "unclear"])
def test_unreviewed_frames_are_not_assumed_empty(status):
    with pytest.raises(ValueError, match="đã duyệt"):
        score_records([{**review(), "review_status": status}], [], {}, {"123": 2023}, 0.5, 32, 96)


def test_missing_prediction_is_error_instead_of_zero_detections():
    with pytest.raises(ValueError, match="thiếu dự đoán"):
        score_records([review()], [], {"P-102": "P.102"}, {"123": 2023}, 0.5, 32, 96)


def test_duplicate_annotation_ids_cannot_double_metric_denominator():
    predicted = {"image_id": "123", "image_sha256": "same", "boxes": []}
    with pytest.raises(ValueError, match="trùng"):
        score_records(
            [review(), review()], [predicted], {"P-102": "P.102"}, {"123": 2023}, 0.5, 32, 96
        )


def test_mapping_requires_all_original_output_labels_to_be_reviewed():
    assert reviewed_mapping(decisions(), {"P-102", "other"}) == {"P-102": "P.102", "other": None}
    with pytest.raises(ValueError, match="toàn bộ"):
        reviewed_mapping(decisions()[:1], {"P-102", "other"})
    unconfirmed = deepcopy(decisions())
    unconfirmed[0]["review_status"] = "assistant_suggested"
    with pytest.raises(ValueError, match="người duyệt"):
        reviewed_mapping(unconfirmed, {"P-102", "other"})


@pytest.mark.parametrize(
    "length,expected", [(31.9, "small"), (32, "medium"), (95.9, "medium"), (96, "large")]
)
def test_size_buckets_use_actual_gt_short_side(length, expected):
    assert size_bucket([0, 0, length, length * 2], 32, 96) == expected


@pytest.mark.parametrize("confidence", [True, float("nan"), -0.1, 1.1])
def test_invalid_confidence_is_rejected(confidence):
    with pytest.raises(ValueError, match="Confidence"):
        checked_box(box(confidence=confidence), 100, 100, True)


def evaluation_fixture(root):
    report = root / "reports/stage0"
    write_json(root / "config/survey-class-candidates.yaml", {"poc_mapping_decisions": decisions()})
    write_json(
        root / "config/params.yaml",
        {
            "poc_iou_threshold": {"value": 0.5},
            "poc_small_bbox_px": {"value": 32},
            "poc_medium_bbox_px": {"value": 96},
        },
    )
    lock = [{"image_id": "123", "year": 2023}]
    lock_hash = stable_hash(lock)
    write_json(
        root / "data/private/samples/sample-lock.json",
        {"images": lock, "sample_ids_hash": lock_hash},
    )
    image = root / "data/private/samples/images/123.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"synthetic hash fixture, never real survey image")
    record = {**review(), "image_sha256": sha256_file(image)}
    write_jsonl(root / "data/private/samples/annotation-template.jsonl", [record])
    write_jsonl(root / "data/private/samples/manual-review.jsonl", [record])
    prediction = root / "data/private/poc/predictions.jsonl"
    write_jsonl(
        prediction,
        [
            {
                "image_id": "123",
                "year": 2023,
                "image_sha256": record["image_sha256"],
                "boxes": [box(label="P-102")],
            }
        ],
    )
    write_json(
        report / "poc-manifest.json",
        {"sample_ids_hash": lock_hash, "output_labels": ["P-102", "other"]},
    )
    write_json(
        report / "sample-manifest.json",
        {"sample_ids_hash": lock_hash, "predictions_sha256": sha256_file(prediction)},
    )
    return report


def test_evaluation_integration_records_hashes_without_heavy_libraries(tmp_path):
    report = evaluation_fixture(tmp_path)
    result = evaluate_poc(tmp_path)
    assert result["metrics_valid"] and result["status"] == "all_images_reviewed"
    assert result["recall"] == 1 and result["negative_evidence_enabled"] is False
    assert len(result["outputs"]) == 2
    assert read_json(report / "poc-evaluation.json")["reviewed_images"] == 1


def test_missing_manual_labels_invalidates_stale_metrics_in_manifest(tmp_path):
    report = evaluation_fixture(tmp_path)
    evaluate_poc(tmp_path)
    (tmp_path / "data/private/samples/manual-review.jsonl").unlink()
    result = evaluate_poc(tmp_path)
    assert result["status"] == "not_run" and result["recall"] is None
    assert result["outputs"] == [] and result["metrics_valid"] is False
    assert (report / "poc-review-metrics.csv").exists()  # Tệp cũ không được coi còn hiệu lực.


def test_evaluation_rejects_prediction_hash_changed_after_poc(tmp_path):
    report = evaluation_fixture(tmp_path)
    evaluate_poc(tmp_path)
    with (tmp_path / "data/private/poc/predictions.jsonl").open("a") as output:
        output.write("\n")
    with pytest.raises(ValueError, match="Hash dự đoán"):
        evaluate_poc(tmp_path)
    assert read_json(report / "poc-evaluation.json")["metrics_valid"] is False
