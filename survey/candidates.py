"""Giao của nhãn gợi ý và annotation gốc; không xác nhận lớp hay biển vật lý."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .io import (
    implementation_manifest,
    read_json,
    read_yaml,
    sha256_file,
    stable_hash,
    write_csv,
    write_json,
)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def build_matrix(
    classes: list[dict], routes: list[dict], years: list[int], labels: list[dict], hints: list[dict]
) -> list[dict]:
    codes = [item["code"] for item in classes]
    if len(set(codes)) != len(codes):
        raise ValueError("Danh sách ứng viên còn mã trùng.")
    route_ids = [row["route"] for row in routes]
    label_keys = [(row["original_label"], row["original_split"]) for row in labels]
    hint_keys = [(row["route"], row["hint_label"], int(row["year"])) for row in hints]
    if any(len(set(keys)) != len(keys) for keys in (route_ids, label_keys, hint_keys)):
        raise ValueError("Đầu vào còn khóa tuyến, nhãn/split hoặc nhãn gợi ý/năm bị trùng.")
    if len(set(years)) != len(years) or not years:
        raise ValueError("Danh sách năm cần duy nhất và không rỗng.")
    known_labels = {row["original_label"] for row in labels}
    result = []
    for route in routes:
        for candidate in classes:
            original = candidate["original_labels"]
            if set(original) - known_labels:
                raise ValueError("Ứng viên trỏ nhãn gốc không tồn tại trong bản audit dataset.")
            counts = {
                split: sum(
                    int(row["object_count"])
                    for row in labels
                    if row["original_label"] in original and row["original_split"] == split
                )
                for split in ("train", "val", "test")
            }
            for year in years:
                matching = [
                    row
                    for row in hints
                    if row["route"] == route["route"]
                    and int(row["year"]) == year
                    and row["hint_label"] in candidate["hints"]
                ]
                result.append(
                    {
                        "route": route["route"],
                        "candidate_qcvn": candidate["code"],
                        "year": year,
                        "original_labels": ";".join(original),
                        "raw_train_objects": counts["train"],
                        "raw_val_objects": counts["val"],
                        "raw_test_objects": counts["test"],
                        "feature_hints": sum(int(row["feature_hint_count"]) for row in matching),
                        "hints_with_passing_images": sum(
                            int(row["hints_with_passing_images"]) for row in matching
                        ),
                        "hints_with_ge2_passing_creators": sum(
                            int(row["hints_with_ge2_passing_creators"]) for row in matching
                        ),
                        "mapping_review": candidate["mapping_review"],
                        "confirmed_route_objects": None,
                        "confirmed_train_objects": None,
                        "gate_status": "needs_independent_review",
                        "note": candidate.get("note", "Chưa đối chiếu toàn bộ crop và ảnh tuyến."),
                    }
                )
    return result


def summarize_routes(matrix: list[dict], routes: list[dict], years: list[int]) -> list[dict]:
    result = []
    for route in routes:
        grouped = defaultdict(list)
        for row in matrix:
            if row["route"] == route["route"]:
                grouped[row["candidate_qcvn"]].append(row)
        complete, with_train = [], []
        for code, entries in grouped.items():
            if {row["year"] for row in entries} != set(years):
                raise ValueError("Bảng tuyến/lớp thiếu một năm; không được coi là đủ dữ liệu.")
            if all(row["hints_with_passing_images"] > 0 for row in entries):
                complete.append(code)
                if all(row["raw_train_objects"] > 0 for row in entries):
                    with_train.append(code)
        result.append(
            {
                "route": route["route"],
                "length_m": route["length_m"],
                "candidate_classes_with_hints_all_years": len(complete),
                "candidate_classes_with_raw_train_and_hints_all_years": len(with_train),
                "candidate_codes": ";".join(sorted(with_train)),
                "confirmed_eligible_classes": None,
                "status": "not_approved",
                "interpretation": "search_priority_only_not_verified_class_coverage",
            }
        )
    return result


def candidate_report(root: Path) -> dict:
    report = root / "reports/stage0"
    dataset = report / "datasets/vietnam-traffic-sign-altsi-v3"
    paths = [
        root / "config/survey-class-candidates.yaml",
        root / "config/survey.yaml",
        report / "routes/candidates.csv",
        report / "route-hint-summary.csv",
        dataset / "label-counts.csv",
        dataset / "dataset-manifest.json",
    ]
    configuration = read_yaml(paths[0])
    if configuration["status"] != "pending_user_approval":
        raise ValueError("Bảng khảo sát phải giữ trạng thái đề xuất, chưa chốt danh mục lớp.")
    manifest = read_json(paths[-1])
    if not manifest.get("inventory_hash"):
        raise ValueError("Thiếu hash inventory kiểm đếm annotation thực.")
    routes, years = read_csv(paths[2]), read_yaml(paths[1])["years"]
    matrix = build_matrix(
        configuration["classes"], routes, years, read_csv(paths[4]), read_csv(paths[3])
    )
    summaries = summarize_routes(matrix, routes, years)
    write_csv(report / "route-class-candidates.csv", list(matrix[0]), matrix)
    write_csv(report / "route-candidate-comparison.csv", list(summaries[0]), summaries)
    lines = [
        "# Bảng tuyến và lớp để duyệt",
        "",
        "Đây là bảng ưu tiên kiểm ảnh. Chưa có lớp nào được xác nhận đủ điều kiện.",
        "Số trong cột tuyến là số feature gợi ý có ảnh đi qua theo từng năm,",
        "lấy giá trị nhỏ nhất của ba năm. Đây không phải số biển đã thấy đúng mã.",
        "",
        "| Mã ứng viên | Object train gốc | Hàng Bài | Trần Quang Khải | Tràng Thi | Ánh xạ |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for candidate in configuration["classes"]:
        entries = [row for row in matrix if row["candidate_qcvn"] == candidate["code"]]
        values = [
            min(
                row["hints_with_passing_images"]
                for row in entries
                if row["route"] == route["route"]
            )
            for route in routes
        ]
        lines.append(
            f"| {candidate['code']} | {entries[0]['raw_train_objects']} | "
            + " | ".join(map(str, values))
            + f" | {candidate['mapping_review']} |"
        )
    lines.extend(
        [
            "",
            "Mỗi mã vẫn cần duyệt crop và bbox ảnh tuyến cho 2023/2024/2025.",
            "Số train chưa khử trùng; không lấy số này làm lượng mẫu hợp lệ cuối.",
            "Danh sách hiện có 18 mã để so sánh; chưa phải danh mục 10–15 mã đã chọn.",
            "Không tự thay dấu gạch ngang trong nhãn nguồn bằng dấu chấm rồi coi đó là mã đúng.",
        ]
    )
    (report / "route-class-review.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    result = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "stage0_search_priority_only",
        "status": "pending_independent_review_and_user_approval",
        **implementation_manifest(),
        "candidate_class_count": len(configuration["classes"]),
        "years": years,
        "matrix_hash": stable_hash(matrix),
        "dataset_inventory_hash": manifest["inventory_hash"],
        "inputs": [
            {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
            for path in paths
        ],
        "outputs": [
            {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
            for path in (
                report / "route-class-candidates.csv",
                report / "route-candidate-comparison.csv",
                report / "route-class-review.md",
            )
        ],
        "route_approved": False,
        "classes_approved": False,
        "negative_evidence_enabled": False,
        "limitations": [
            "Nhãn Mapillary chỉ là gợi ý; ảnh đi qua không xác nhận biển trong ảnh.",
            "Số object dataset là số gốc, chưa khử trùng hay xác nhận ánh xạ QCVN.",
            "Không chọn 10–15 lớp bằng số feature gợi ý.",
        ],
    }
    write_json(report / "candidate-manifest.json", result)
    return result
