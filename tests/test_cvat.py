import xml.etree.ElementTree as ET
import zipfile

import pytest

from survey.cvat import annotation_xml, export_cvat, import_cvat
from survey.io import read_json, read_jsonl, sha256_file, stable_hash, write_json, write_jsonl


@pytest.fixture
def cvat_root(tmp_path):
    samples = tmp_path / "data/private/samples"
    images, template = [], []
    for identity in ("101", "102", "103"):
        image = samples / "images" / f"{identity}.jpg"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(f"synthetic-image-{identity}".encode())
        images.append(
            {
                "image_id": identity,
                "year": 2023,
                "routes": ["hang_bai" if identity != "103" else "other"],
            }
        )
        template.append(
            {
                "image_id": identity,
                "image_sha256": sha256_file(image),
                "width_px": 100,
                "height_px": 100,
                "review_status": "pending",
                "boxes": [],
                "label_source": "manual_required",
            }
        )
    write_json(
        samples / "sample-lock.json", {"images": images, "sample_ids_hash": stable_hash(images)}
    )
    write_jsonl(samples / "annotation-template.jsonl", template)
    config = tmp_path / "config/survey-class-candidates.yaml"
    config.parent.mkdir()
    config.write_text("classes:\n  - code: P.102\n  - code: W.209\n", encoding="utf-8")
    return tmp_path


def xml_file(root, state="LS_REVIEWED", box=True):
    tree = ET.Element("annotations")
    ET.SubElement(tree, "version").text = "1.1"
    first = ET.SubElement(tree, "image", id="0", name="images/101.jpg", width="100", height="100")
    if box:
        ET.SubElement(
            first, "box", label="P.102", xtl="10", ytl="20", xbr="40", ybr="60", source="manual"
        )
    if state:
        ET.SubElement(first, "tag", label=state, source="manual")
    ET.SubElement(tree, "image", id="1", name="102.jpg", width="100", height="100")
    path = root / "annotations.xml"
    ET.ElementTree(tree).write(path, encoding="utf-8", xml_declaration=True)
    return path, tree


def test_export_original_images_and_provisional_labels(cvat_root):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    manifest = read_json(package / "manifest.json")
    assert manifest["classes_finalized"] is False
    assert len(manifest["images"]) == 2
    with zipfile.ZipFile(package / "images.zip") as archive:
        assert archive.namelist() == ["101.jpg", "102.jpg"]
        assert archive.read("101.jpg") == b"synthetic-image-101"
    labels = {label["name"]: label for label in read_json(package / "labels.json")}
    assert labels["P.102"]["type"] == "rectangle"
    assert labels["LS_UNCLEAR"]["type"] == "tag"
    assert labels["QCVN_OTHER"]["attributes"][0]["name"] == "qcvn"
    assert export_cvat(cvat_root, "hang_bai", 2023) == package


def test_export_rejects_changed_original_or_changed_package(cvat_root):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    (package / "labels.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Gói CVAT đã đổi"):
        export_cvat(cvat_root, "hang_bai", 2023)
    (cvat_root / "data/private/samples/images/101.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Ảnh đã đổi"):
        export_cvat(cvat_root, "hang_bai", 2023)


@pytest.mark.parametrize(
    "state,boxes,count,status",
    [
        ("LS_REVIEWED", True, 1, "reviewed"),
        ("LS_EMPTY_CONFIRMED", False, 1, "reviewed"),
        ("LS_UNCLEAR", True, 0, "unclear"),
        (None, True, 0, None),
    ],
)
def test_import_requires_explicit_image_status(cvat_root, state, boxes, count, status):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    path, _ = xml_file(cvat_root, state, boxes)
    assert import_cvat(cvat_root, path, package) == count
    rows = read_jsonl(cvat_root / "data/private/samples/manual-review.jsonl")
    if status:
        assert rows[0]["review_status"] == status
        assert rows[0]["explicit_empty"] == (state == "LS_EMPTY_CONFIRMED")
    else:
        assert rows == []  # Draft bbox without a reviewed tag never enters GT.


def test_import_partial_task_preserves_previous_and_keeps_backup(cvat_root):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    template = read_jsonl(cvat_root / "data/private/samples/annotation-template.jsonl")
    previous = [
        {**row, "review_status": "reviewed", "explicit_empty": True, "label_source": "manual"}
        for row in template[1:]
    ]
    canonical = cvat_root / "data/private/samples/manual-review.jsonl"
    write_jsonl(canonical, previous)
    previous_hash = sha256_file(canonical)
    path, _ = xml_file(cvat_root)
    assert import_cvat(cvat_root, path, package) == 3
    actual = {row["image_id"]: row for row in read_jsonl(canonical)}
    assert actual["102"] == previous[0] and actual["103"] == previous[1]
    assert actual["101"]["boxes"][0]["bbox_xyxy"] == [10, 20, 40, 60]
    assert (cvat_root / f"data/private/cvat/imports/previous-{previous_hash}.jsonl").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign",
        "traversal",
        "size",
        "auto_box",
        "auto_tag",
        "rotated",
        "polygon",
        "contradictory_tags",
        "unknown_label",
        "nan",
        "out_of_bounds",
    ],
)
def test_import_rejects_ambiguous_or_invalid_records_without_overwriting(cvat_root, mutation):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    path, tree = xml_file(cvat_root)
    image = tree.findall("image")[0]
    box = image.find("box")
    assert box is not None
    if mutation == "missing":
        tree.remove(tree.findall("image")[1])
    elif mutation == "duplicate":
        tree.findall("image")[1].set("name", "101.jpg")
    elif mutation == "foreign":
        image.set("name", "999.jpg")
    elif mutation == "traversal":
        image.set("name", "../101.jpg")
    elif mutation == "size":
        image.set("width", "101")
    elif mutation == "auto_box":
        box.set("source", "auto")
    elif mutation == "auto_tag":
        image.find("tag").set("source", "auto")
    elif mutation == "rotated":
        box.set("rotation", "15")
    elif mutation == "polygon":
        box.tag = "polygon"
    elif mutation == "contradictory_tags":
        ET.SubElement(image, "tag", label="LS_UNCLEAR")
    elif mutation == "unknown_label":
        box.set("label", "unknown")
    elif mutation == "nan":
        box.set("xtl", "nan")
    elif mutation == "out_of_bounds":
        box.set("xbr", "101")
    ET.ElementTree(tree).write(path, encoding="utf-8")
    with pytest.raises(ValueError):
        import_cvat(cvat_root, path, package)
    assert not (cvat_root / "data/private/samples/manual-review.jsonl").exists()


@pytest.mark.parametrize("state,box", [("LS_REVIEWED", False), ("LS_EMPTY_CONFIRMED", True)])
def test_empty_images_require_dedicated_confirmation(cvat_root, state, box):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    path, _ = xml_file(cvat_root, state, box)
    with pytest.raises(ValueError):
        import_cvat(cvat_root, path, package)


def test_other_qcvn_and_zip_import(cvat_root):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    path, tree = xml_file(cvat_root)
    box = tree.find("image/box")
    assert box is not None
    box.set("label", "QCVN_OTHER")
    ET.SubElement(box, "attribute", name="qcvn").text = "P.103a"
    ET.ElementTree(tree).write(path, encoding="utf-8")
    archive_path = cvat_root / "export.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(path, "annotations.xml")
    assert import_cvat(cvat_root, archive_path, package) == 1
    rows = read_jsonl(cvat_root / "data/private/samples/manual-review.jsonl")
    assert rows[0]["boxes"][0]["label"] == "P.103a"


@pytest.mark.parametrize(
    "text",
    [
        '<!DOCTYPE annotations [<!ENTITY x "boom">]><annotations><version>1.1</version></annotations>',
        "<annotations><version>1.1</version><track/></annotations>",
        "<annotations><version>1.0</version></annotations>",
        "<annotations>",
    ],
)
def test_rejects_dtd_video_wrong_version_and_bad_xml(cvat_root, text):
    path = cvat_root / "bad.xml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        annotation_xml(path)


def test_import_rejects_flipped_task(cvat_root):
    package = export_cvat(cvat_root, "hang_bai", 2023)
    path, tree = xml_file(cvat_root)
    task = ET.SubElement(ET.SubElement(tree, "meta"), "task")
    ET.SubElement(task, "flipped").text = "True"
    ET.ElementTree(tree).write(path, encoding="utf-8")
    with pytest.raises(ValueError, match="lật ảnh"):
        import_cvat(cvat_root, path, package)
