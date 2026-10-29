"""Tạo crop để xem nhãn gốc; không tự quyết định ánh xạ QCVN."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

from .io import read_json, read_jsonl, stable_hash, write_csv


def crop_sheets(directory: Path, report: Path, output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    manifest = read_json(report / "dataset-manifest.json")
    inventory = read_jsonl(report / "image-inventory.jsonl")
    by_class = defaultdict(list)
    for image in inventory:
        for index, box in enumerate(image["objects"]):
            by_class[box["class_id"]].append((image, index, box))
    font_path = Path("C:/Windows/Fonts/segoeui.ttf")
    font = (
        ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    )
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for page in range(math.ceil(len(manifest["class_names"]) / 14)):
        sheet = Image.new("RGB", (1200, 1160), "#f6f8fb")
        draw = ImageDraw.Draw(sheet)
        for local_index, label_id in enumerate(
            range(page * 14, min((page + 1) * 14, len(manifest["class_names"])))
        ):
            name = manifest["class_names"][label_id]
            candidates = sorted(
                by_class[label_id], key=lambda item: stable_hash([item[0]["image_key"], item[1]])
            )[:3]
            left, top = (local_index % 2) * 600, (local_index // 2) * 160
            draw.text((left + 12, top + 6), f"Nhãn gốc: {name}", font=font, fill="#173253")
            for slot, (image, box_index, box) in enumerate(candidates):
                relative = image["image_key"].split(":", 1)[1]
                with Image.open(directory / relative) as source:
                    source = source.convert("RGB")
                    cx, cy, width, height = box["xywh"]
                    rectangle = (
                        math.floor((cx - width / 2) * source.width),
                        math.floor((cy - height / 2) * source.height),
                        math.ceil((cx + width / 2) * source.width),
                        math.ceil((cy + height / 2) * source.height),
                    )
                    crop = source.crop(rectangle)
                    crop = ImageOps.contain(crop, (180, 112), Image.Resampling.LANCZOS)
                    sheet.paste(crop, (left + slot * 195 + 12, top + 38))
                rows.append(
                    {
                        "original_label_id": label_id,
                        "original_label": name,
                        "image_key": image["image_key"],
                        "box_index": box_index,
                        "sheet": f"labels-{page + 1}.png",
                        "review_status": "pending",
                        "qcvn_code": "",
                        "mixed_codes": "cần xem",
                    }
                )
        draw.text(
            (12, 1130),
            "Nguồn: giang / Roboflow Universe, vietnam-traffic-sign-altsi v3, CC BY 4.0. Ảnh đã cắt crop.",
            font=ImageFont.truetype(str(font_path), 14) if font_path.exists() else font,
            fill="#526980",
        )
        sheet.save(output / f"labels-{page + 1}.png")
    write_csv(report / "crop-review.csv", list(rows[0]), rows)
    print(f"Đã tạo {math.ceil(len(manifest['class_names']) / 14)} ảnh ghép từ crop thật.")
