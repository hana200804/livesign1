import pytest

from survey.io import read_json, stable_hash, write_csv, write_json, write_jsonl
from survey.review import build_review, import_review


def fixture_root(root):
    images = [{"image_id": "123", "year": 2023, "routes": ["r"], "creator_id": "photographer"}]
    write_json(
        root / "data/private/samples/sample-lock.json",
        {"images": images, "sample_ids_hash": stable_hash(images)},
    )
    write_json(root / "config/survey.yaml", {"route_seeds": [{"id": "r", "name": "Fixture route"}]})
    path = root / "reports/stage0/sample-quality.csv"
    row = {"image_id": "123", "width_px": 100, "height_px": 100, "image_sha256": "fixture"}
    write_csv(path, list(row), [row])
    return path, row


def test_build_review_uses_locked_ids_and_route_names(tmp_path):
    fixture_root(tmp_path)
    page = build_review(tmp_path).read_text(encoding="utf-8")
    assert '"sample_ids_hash"' in page and '"Fixture route"' in page
    assert "__SURVEY_DATA__" not in page


def test_missing_sample_quality_does_not_make_incomplete_review_page(tmp_path):
    path, row = fixture_root(tmp_path)
    write_csv(path, list(row), [])
    with pytest.raises(ValueError, match="thiếu ảnh"):
        build_review(tmp_path)


def test_duplicate_sample_id_does_not_silently_replace_its_hash(tmp_path):
    path, row = fixture_root(tmp_path)
    write_csv(path, list(row), [row, {**row, "image_sha256": "different"}])
    with pytest.raises(ValueError, match="ID trùng"):
        build_review(tmp_path)


def test_changed_sample_lock_blocks_page_and_annotation_import(tmp_path):
    fixture_root(tmp_path)
    write_json(
        tmp_path / "data/private/samples/sample-lock.json", {"images": [], "sample_ids_hash": "old"}
    )
    with pytest.raises(ValueError, match="đã đổi"):
        build_review(tmp_path)
    path = tmp_path / "export.json"
    write_json(path, {})
    with pytest.raises(ValueError, match="đã đổi"):
        import_review(tmp_path, path)


def test_annotation_template_cannot_replace_locked_image_ids(tmp_path):
    fixture_root(tmp_path)
    lock = read_json(tmp_path / "data/private/samples/sample-lock.json")
    export = tmp_path / "export.json"
    write_json(
        export,
        {
            "sample_ids_hash": lock["sample_ids_hash"],
            "annotation_origin": "human_review_ui",
            "images": [],
        },
    )
    write_jsonl(
        tmp_path / "data/private/samples/annotation-template.jsonl", [{"image_id": "another"}]
    )
    with pytest.raises(ValueError, match="Template gán nhãn"):
        import_review(tmp_path, export)
