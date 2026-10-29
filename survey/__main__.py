"""Chạy bằng python -m survey. Mỗi lệnh chỉ xử lý Giai đoạn 0."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from .geometry import padded_bbox
from .io import (
    implementation_manifest,
    load_env,
    read_json,
    read_jsonl,
    read_yaml,
    sha256_file,
    stable_hash,
    write_csv,
    write_json,
    write_jsonl,
)
from .metrics import (
    coverage,
    feature_rows,
    normalize_images,
    region_rows,
    route_quality,
    summarize_hints,
)
from .network import Mapillary, SurveyError, fetch_osm_map
from .osm import make_route, road_lines

ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="LiveSign — khảo sát dữ liệu trước khi chọn tuyến và lớp."
    )
    result.add_argument(
        "--root", type=Path, default=ROOT, help="Thư mục dự án chứa .env và config/."
    )
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Kiểm tra cấu hình; chỉ hiển thị key có/không.")
    for name in ("fetch-osm", "fetch-images", "fetch-features", "routes", "report"):
        command = commands.add_parser(name)
        command.add_argument(
            "--region", default="all", help="hoan_kiem, cau_giay, ha_dong hoặc all."
        )
    audit = commands.add_parser(
        "audit-dataset", help="Đếm object thực trong bản xuất YOLO có giấy phép rõ."
    )
    audit.add_argument("--directory", type=Path, required=True)
    audit.add_argument(
        "--source", type=Path, required=True, help="YAML xác định URL, phiên bản và giấy phép."
    )
    audit.add_argument("--output", type=Path, required=True)
    download = commands.add_parser(
        "download-dataset", help="Tải bản YOLOv8 Roboflow có giấy phép rõ."
    )
    download.add_argument("--workspace", required=True)
    download.add_argument("--project", required=True)
    download.add_argument("--version", type=int, required=True)
    samples = commands.add_parser(
        "collect-samples", help="Khóa mẫu theo tuyến/năm, tải ảnh và đo kích thước thật."
    )
    samples.add_argument("--per-year", type=int, default=12)
    commands.add_parser("poc", help="Chạy detector ONNX có sẵn trên mẫu đã khóa; không train.")
    commands.add_parser("prepare-poc", help="Tải detector PoC ở revision cố định và kiểm SHA-256.")
    commands.add_parser(
        "candidate-report", help="Đối chiếu nhãn gợi ý với số object dataset, chưa chốt lớp."
    )
    commands.add_parser(
        "evaluate-poc", help="Chấm PoC chỉ khi có bbox và ánh xạ nhãn đã duyệt độc lập."
    )
    commands.add_parser("build-review", help="Xuất giao diện gán bbox thủ công cho mẫu đã khóa.")
    review_import = commands.add_parser(
        "import-review", help="Kiểm tra và nhập JSON gán tay do người dùng xuất."
    )
    review_import.add_argument("--file", type=Path, required=True)
    crops = commands.add_parser("crop-sheets", help="Tạo ảnh ghép crop cho từng nhãn gốc dataset.")
    crops.add_argument("--directory", type=Path, required=True)
    crops.add_argument("--report", type=Path, required=True)
    crops.add_argument("--output", type=Path, required=True)
    return result


def selected_regions(config: dict, selection: str) -> dict:
    if selection == "all":
        return config["regions"]
    if selection not in config["regions"]:
        raise ValueError("Vùng không có trong config/survey.yaml.")
    return {selection: config["regions"][selection]}


def parameter(config: dict, name: str):
    entry = config[name]
    if entry.get("status") not in ("đã chốt", "dự kiến"):
        raise ValueError(f"Tham số thiếu status hợp lệ: {name}")
    return entry["value"]


def manifest(root: Path, inputs: list[Path], status: str) -> dict:
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "run_id": "survey-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"),
        "python_version": platform.python_version(),
        **implementation_manifest(),
        "inputs": [
            {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
            for path in inputs
        ],
        "attribution": ["© Mapillary contributors", "© OpenStreetMap contributors"],
        "route_approved": False,
        "classes_approved": False,
        "negative_evidence_enabled": False,
    }


def doctor(root: Path) -> None:
    config = read_yaml(root / "config/survey.yaml")
    params = read_yaml(root / "config/params.yaml")
    for key in params:
        parameter(params, key)
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "stage": 0,
                "keys_present": {
                    name: bool(os.environ.get(name))
                    for name in ("MAPILLARY_TOKEN", "ROBOFLOW_API_KEY", "VIETMAP_API_KEY")
                },
                "years": config["years"],
                "regions": list(config["regions"]),
                "optional_pillow_installed": importlib.util.find_spec("PIL") is not None,
                "negative_evidence_enabled": parameter(params, "negative_evidence_enabled"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def routes(root: Path, config: dict, params: dict, selection: str) -> None:
    selected = selected_regions(config, selection)
    output = root / "reports/stage0/routes"
    summaries = []
    failures = []
    for seed in config["route_seeds"]:
        if seed["region"] not in selected:
            continue
        document = read_json(root / "data/cache" / seed["region"] / "osm.json")
        try:
            feature = make_route(
                document,
                seed,
                parameter(params, "route_anchor_max_distance_m"),
                parameter(params, "route_target_length_m"),
            )
            feature["properties"]["input_osm_sha256"] = sha256_file(
                root / "data/cache" / seed["region"] / "osm.json"
            )
            feature["properties"]["seed_hash"] = stable_hash(seed)
        except ValueError as error:
            failures.append({"route": seed["id"], "reason": str(error)})
            continue
        write_json(output / f"{seed['id']}.geojson", feature)
        properties = feature["properties"]
        summaries.append(
            {
                "route": seed["id"],
                "name": seed["name"],
                "region": seed["region"],
                "length_m": properties["length_m"],
                "status": "candidate",
                "max_anchor_offset_m": max(properties["anchor_snap_distances_m"]),
            }
        )
        print(f"Tuyến ứng viên {seed['id']}: {properties['length_m']:.1f} m.")
    if summaries:
        write_csv(output / "candidates.csv", list(summaries[0]), summaries)
    write_json(output / "route-errors.json", failures)
    if failures:
        raise SurveyError(
            "Một số điểm neo chưa tạo được tuyến. Xem route-errors.json; chưa chọn tuyến demo."
        )


def report(root: Path, config: dict, params: dict, selection: str) -> None:
    radius = parameter(params, "survey_radius_m")
    step = parameter(params, "road_sample_step_m")
    region_output, quality_output, feature_output = [], [], []
    inputs = [root / "config/survey.yaml", root / "config/params.yaml"]
    for region_id, region in selected_regions(config, selection).items():
        cache = root / "data/cache" / region_id
        required = [
            cache / "osm.json",
            cache / "images.jsonl",
            cache / "features.jsonl",
            cache / "osm-manifest.json",
            cache / "images-manifest.json",
            cache / "features-manifest.json",
        ]
        if any(not path.exists() for path in required):
            raise SurveyError(
                f"Vùng {region_id} thiếu đầu vào. Chạy đủ fetch-osm/images/features trước."
            )
        osm_manifest = read_json(cache / "osm-manifest.json")
        if osm_manifest.get("bbox") != region["bbox"] or osm_manifest.get(
            "data_sha256"
        ) != sha256_file(cache / "osm.json"):
            raise SurveyError(
                f"Vùng {region_id}: cache OSM khác cấu hình hoặc hash không khớp. Chạy lại fetch-osm."
            )
        for kind in ("images", "features"):
            collected = read_json(cache / f"{kind}-manifest.json")
            expected = collection_spec(config, params, region_id, kind)
            if (
                collected.get("query_spec_hash") != stable_hash(expected)
                or collected.get("status") != "complete"
            ):
                raise SurveyError(
                    f"Vùng {region_id}: cache {kind} khác cấu hình hoặc chưa tải đủ. Cần chạy lại."
                )
            if collected.get("data_sha256") != sha256_file(cache / f"{kind}.jsonl"):
                raise SurveyError(f"Vùng {region_id}: hash cache {kind} không khớp.")
        images = normalize_images(read_jsonl(cache / "images.jsonl"), config["years"])
        lines = road_lines(read_json(cache / "osm.json"), region["bbox"])
        covered = coverage(images, lines, config["years"], radius, step)
        region_output.extend(
            region_rows(region_id, region["bbox"], images, config["years"], covered)
        )
        inputs.extend(required)
        for seed in config["route_seeds"]:
            route_path = root / "reports/stage0/routes" / f"{seed['id']}.geojson"
            if seed["region"] != region_id or not route_path.exists():
                continue
            route = read_json(route_path)
            if route["properties"].get("input_osm_sha256") != sha256_file(
                cache / "osm.json"
            ) or route["properties"].get("seed_hash") != stable_hash(seed):
                raise SurveyError(
                    "Tuyến ứng viên khác nguồn OSM hoặc cấu hình hiện tại. Chạy lại routes."
                )
            quality_output.extend(route_quality(route, images, config["years"], radius))
            feature_output.extend(
                feature_rows(
                    route, read_jsonl(cache / "features.jsonl"), images, config["years"], radius
                )
            )
            inputs.append(route_path)
    output = root / "reports/stage0"
    write_csv(output / "region-coverage.csv", list(region_output[0]), region_output)
    if quality_output:
        write_csv(output / "route-quality.csv", list(quality_output[0]), quality_output)
    fields = [
        "route",
        "feature_id",
        "hint_label",
        "year",
        "lon",
        "lat",
        "image_count",
        "sequence_count",
        "creator_count",
        "creator_year_pair_count",
        "missing_creator_images",
        "interpretation",
    ]
    write_csv(output / "route-feature-years.csv", fields, feature_output)
    hint_summary = summarize_hints(feature_output)
    if hint_summary:
        write_csv(output / "route-hint-summary.csv", list(hint_summary[0]), hint_summary)
    write_json(
        output / "survey-manifest.json",
        manifest(root, inputs, "awaiting_manual_review_and_route_class_approval"),
    )
    print(f"Đã xuất {len(region_output)} dòng vùng–năm và {len(feature_output)} dòng feature–năm.")


def collection_spec(config: dict, params: dict, region_id: str, kind: str) -> dict:
    region = config["regions"][region_id]
    return {
        "kind": kind,
        "bbox": padded_bbox(region["bbox"], parameter(params, "survey_radius_m")),
        "years": config["years"] if kind == "images" else None,
        "source": "mapillary_vector_tiles",
        "zoom": 14,
    }


def fetch(root: Path, config: dict, params: dict, command: str, selection: str) -> None:
    client = Mapillary() if command != "fetch-osm" else None
    for region_id, region in selected_regions(config, selection).items():
        output = root / "data/cache" / region_id
        if command == "fetch-osm":
            document = fetch_osm_map(region["bbox"], root / "data/cache/osm-tiles")
            write_json(output / "osm.json", document)
            write_json(
                output / "osm-manifest.json",
                {
                    "bbox": region["bbox"],
                    "data_sha256": sha256_file(output / "osm.json"),
                    "osm_base_timestamp": document.get("osm3s", {}).get("timestamp_osm_base"),
                    "created_at_utc": datetime.now(UTC).isoformat(),
                },
            )
            print(f"{region_id}: {len(road_lines(document, region['bbox']))} đoạn đường OSM.")
            continue
        kind = "images" if command == "fetch-images" else "features"
        spec = collection_spec(config, params, region_id, kind)
        if client is None:
            raise ValueError("Chưa tạo client thu thập Mapillary.")
        rows = client.tile_entities(spec["bbox"], kind, root / "data/cache/tiles")
        if kind == "images":
            from .metrics import captured_year

            rows = [row for row in rows if captured_year(row["captured_at"]) in config["years"]]
            normalize_images(rows, config["years"])
        write_jsonl(output / f"{kind}.jsonl", rows)
        write_json(
            output / f"{kind}-manifest.json",
            {
                "status": "complete",
                "query_spec": spec,
                "query_spec_hash": stable_hash(spec),
                "row_count": len(rows),
                "data_sha256": sha256_file(output / f"{kind}.jsonl"),
                "created_at_utc": datetime.now(UTC).isoformat(),
            },
        )
        print(f"{region_id}: {len(rows)} {kind}; đã đọc các tile phủ vùng.")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        load_env(root / ".env")
        if args.command == "doctor":
            doctor(root)
            return 0
        if args.command == "candidate-report":
            from .candidates import candidate_report

            result = candidate_report(root)
            print(
                f"Đã lập bảng {result['candidate_class_count']} mã ứng viên; chưa chốt lớp hay tuyến."
            )
            return 0
        if args.command == "evaluate-poc":
            from .evaluation import evaluate_poc

            result = evaluate_poc(root)
            summary = {key: result[key] for key in ("status", "recall", "metrics_valid", "reasons")}
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if result["status"] != "not_run" else 2
        if args.command == "build-review":
            from .review import build_review

            print(f"Đã tạo giao diện duyệt: {build_review(root).relative_to(root)}")
            return 0
        if args.command == "import-review":
            from .review import import_review

            count = import_review(root, args.file.resolve())
            print(f"Đã nhập {count} ảnh đã duyệt. Không tạo observation not_seen.")
            return 0
        if args.command == "audit-dataset":
            from .datasets import audit_dataset

            audit_dataset(args.directory.resolve(), read_yaml(args.source), args.output.resolve())
            print("Đã kiểm đếm annotation thực. Chưa ánh xạ nhãn hay chia lại dữ liệu.")
            return 0
        if args.command == "download-dataset":
            from .sources import download_roboflow

            directory = download_roboflow(root, args.workspace, args.project, args.version)
            print(f"Đã tải dataset có giấy phép rõ: {directory.relative_to(root)}")
            return 0
        if args.command == "crop-sheets":
            from .media import crop_sheets

            crop_sheets(args.directory.resolve(), args.report.resolve(), args.output.resolve())
            return 0
        config = read_yaml(root / "config/survey.yaml")
        params = read_yaml(root / "config/params.yaml")
        if args.command == "prepare-poc":
            from .poc import prepare_poc

            prepare_poc(root)
            return 0
        if args.command == "poc":
            from .poc import run_poc

            run_poc(root, params)
            return 0
        if args.command == "collect-samples":
            from .samples import collect_samples

            collect_samples(root, config, params, args.per_year)
            return 0
        if args.command.startswith("fetch-"):
            fetch(root, config, params, args.command, args.region)
        elif args.command == "routes":
            routes(root, config, params, args.region)
        elif args.command == "report":
            report(root, config, params, args.region)
        return 0
    except (SurveyError, ValueError, KeyError, FileNotFoundError, PermissionError) as error:
        # HTTP và .env đã được chuyển thành lỗi không chứa giá trị bí mật.
        print(f"Chưa hoàn tất: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
