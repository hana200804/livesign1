import struct
import zipfile

import pytest

from survey.datasets import audit_dataset, class_names, discover_images, yolo_objects
from survey.network import SurveyError
from survey.samples import select_sample
from survey.sources import extract_dataset


def png_header(width=640, height=480):
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    )


def source():
    return {
        "id": "fixture",
        "url": "https://example.org/dataset/3",
        "version": "3",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    }


def make_image(root, relative, annotation="0 0.5 0.5 0.2 0.2\n"):
    image = root / relative
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(png_header())
    parts = list(image.relative_to(root).parts)
    parts[parts.index("images")] = "labels"
    label = root.joinpath(*parts).with_suffix(".txt")
    label.parent.mkdir(parents=True, exist_ok=True)
    label.write_text(annotation, encoding="utf-8")


def test_audit_uses_paths_in_both_yolo_layouts_and_counts_objects(tmp_path):
    (tmp_path / "data.yaml").write_text("nc: 2\nnames: [left, right]\n", encoding="utf-8")
    make_image(tmp_path, "images/train/sub/a.png", "0 0.5 0.5 0.2 0.2\n1 0.2 0.2 0.1 0.1\n")
    make_image(tmp_path, "test/images/a.png")
    manifest = audit_dataset(tmp_path, source(), tmp_path / "result")
    assert manifest["image_count"] == 2
    assert manifest["object_count"] == 3
    assert manifest["unique_image_sha256_count"] == 1
    assert manifest["cross_split_duplicate_group_count"] == 1
    assert len(discover_images(tmp_path)) == 2


def test_unknown_license_blocks_download_use(tmp_path):
    specification = {**source(), "license": "Unknown"}
    with pytest.raises(ValueError, match="license"):
        audit_dataset(tmp_path, specification, tmp_path / "result")


@pytest.mark.parametrize(
    "line",
    [
        "0 0.5 0.5 0 0.2",
        "2 0.5 0.5 0.2 0.2",
        "0 0.1 0.5 0.4 0.2",
        "0 nan 0.5 0.1 0.2",
        "0.0 0.5 0.5 0.2 0.2",
    ],
)
def test_invalid_annotation_stops_instead_of_becoming_negative(tmp_path, line):
    path = tmp_path / "labels.txt"
    path.write_text(line, encoding="utf-8")
    with pytest.raises(ValueError):
        yolo_objects(path, 2)


def test_missing_annotation_is_not_an_empty_negative(tmp_path):
    with pytest.raises(ValueError, match="Không tự coi"):
        yolo_objects(tmp_path / "missing.txt", 2)


def test_class_ids_cannot_have_gaps():
    with pytest.raises(ValueError):
        class_names({"names": {0: "a", 2: "b"}})


@pytest.mark.parametrize("member", ["../escape.txt", "C:/escape.txt", "folder\\escape.txt"])
def test_zip_paths_cannot_escape_dataset(tmp_path, member):
    archive = tmp_path / "dataset.zip"
    with zipfile.ZipFile(archive, "w") as output:
        entry = zipfile.ZipInfo("entry")
        entry.filename = member
        output.writestr(entry, "content")
    with pytest.raises(SurveyError):
        extract_dataset(archive, tmp_path / "destination")
    assert not (tmp_path / "escape.txt").exists()


def test_zip_case_collisions_are_rejected_on_windows(tmp_path):
    archive = tmp_path / "dataset.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("train/A.txt", "one")
        output.writestr("train/a.txt", "two")
    with pytest.raises(SurveyError, match="trùng"):
        extract_dataset(archive, tmp_path / "destination")


def test_locked_sample_does_not_depend_on_input_order():
    images = [{"id": str(index), "year": 2023 + index % 3} for index in range(60)]
    selected = select_sample(images, [2023, 2024, 2025], 4, "seed")
    assert selected == select_sample(images[::-1], [2023, 2024, 2025], 4, "seed")
    assert len(selected) == 12
