"""Kiểm tra tệp chuẩn bị đưa lên Git. Không đọc hay in nội dung .env."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKED = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".bin",
    ".h5",
    ".keras",
    ".onnx",
    ".tflite",
    ".zip",
    ".engine",
    ".torchscript",
    ".apk",
}
SECRET_PATTERNS = [
    re.compile(rb"MLY\|[0-9]{5,}\|[A-Za-z0-9_-]{16,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
]


def main() -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    problems = []
    for relative in result.stdout.decode("utf-8").split("\x00"):
        if not relative:
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            problems.append((relative, "tệp bí mật"))
            continue
        if path.suffix.lower() in BLOCKED:
            problems.append((relative, "ảnh/dataset/mô hình/bản dựng không đưa vào Git"))
            continue
        if path.stat().st_size > 3 * 1024**2:
            problems.append((relative, "metadata vượt 3 MiB; cần giữ ngoài Git"))
            continue
        payload = path.read_bytes()
        if any(pattern.search(payload) for pattern in SECRET_PATTERNS):
            problems.append((relative, "có dạng token; chỉ báo tên tệp"))
    for relative, reason in problems:
        print(f"{relative}: {reason}")
    print(f"Kiểm tra Git: {len(problems)} vấn đề.")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
