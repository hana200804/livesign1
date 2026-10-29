"""Tải phiên bản Roboflow có giấy phép rõ và giải nén an toàn trên Windows."""

from __future__ import annotations

import os
import re
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlencode

from .io import sha256_file, write_json
from .network import Http, SurveyError

LICENSE_NAMES = {"CC BY 4.0": "CC-BY-4.0", "CC BY-SA 4.0": "CC-BY-SA-4.0", "CC0": "CC0-1.0"}


def extract_dataset(archive: Path, output: Path) -> None:
    root = output.resolve()
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if len(members) > 150_000 or sum(member.file_size for member in members) > 5 * 1024**3:
            raise SurveyError("Dataset vượt giới hạn giải nén 5 GiB hoặc số lượng tệp cho phép.")
        names = set()
        for member in members:
            name = member.orig_filename
            pure = PurePosixPath(name)
            if (
                pure.is_absolute()
                or PureWindowsPath(name).is_absolute()
                or "\\" in name
                or ".." in pure.parts
                or ":" in name
                or "\x00" in name
                or stat.S_ISLNK(member.external_attr >> 16)
            ):
                raise SurveyError("Archive có đường dẫn hoặc symlink không an toàn.")
            folded = name.rstrip("/").casefold()
            if folded in names:
                raise SurveyError("Archive có khóa tệp trùng trên Windows.")
            names.add(folded)
            target = (root / name).resolve()
            if not target.is_relative_to(root):
                raise SurveyError("Archive trỏ ra ngoài thư mục dataset.")
            if target.exists() and not member.is_dir():
                raise SurveyError("Thư mục đích đã có tệp. Không ghi đè dataset đang có.")
        for member in members:
            source.extract(member, root)


def download_roboflow(root: Path, workspace: str, project: str, version: int) -> Path:
    if (
        not all(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value) for value in (workspace, project))
        or version < 1
    ):
        raise ValueError("Workspace, project hoặc phiên bản Roboflow không hợp lệ.")
    token = os.environ.get("ROBOFLOW_API_KEY")
    if not token:
        raise SurveyError("Cần ROBOFLOW_API_KEY trong .env.")
    http = Http(timeout_s=120)
    base = f"https://api.roboflow.com/{workspace}/{project}"
    secret_query = urlencode({"api_key": token})
    project_info = http.json(base + "?" + secret_query).get("project", {})
    license_name = project_info.get("license")
    if license_name not in LICENSE_NAMES:
        raise SurveyError(
            "Dataset chưa có giấy phép rõ trong danh sách đã kiểm. Dừng trước khi tải ảnh."
        )
    version_info = http.json(f"{base}/{version}?{secret_query}").get("version", {})
    if not version_info.get("id"):
        raise SurveyError("Không xác định được phiên bản Roboflow yêu cầu.")
    output = root / "data/private/datasets" / f"{project}-v{version}"
    if output.exists():
        raise SurveyError("Dataset đích đã tồn tại; dùng audit-dataset trên bản đã tải.")
    exported = http.json(f"{base}/{version}/yolov8?{secret_query}").get("export", {})
    link = exported.get("link")
    if not link:
        raise SurveyError(
            "Bản xuất YOLOv8 chưa có sẵn. Cần tạo bản export trên Roboflow rồi thử lại."
        )
    archive = root / "data/raw" / f"{project}-v{version}.zip"
    http.download(link, archive)
    extract_dataset(archive, output)
    source = {
        "id": f"{project}-v{version}",
        "url": f"https://universe.roboflow.com/{workspace}/{project}/dataset/{version}",
        "version": str(version),
        "version_id": version_info["id"],
        "version_name": version_info.get("name"),
        "license": LICENSE_NAMES[license_name],
        "license_url": f"https://universe.roboflow.com/{workspace}/{project}",
        "license_evidence": {
            "source": "Roboflow project API",
            "declared_value": license_name,
            "checked_at_utc": datetime.now(UTC).isoformat(),
        },
        "archive_sha256": sha256_file(archive),
        "provider_declared_image_count": version_info.get("images"),
        "count_note": "Số từ provider chỉ đối chiếu. Dùng annotation thực để báo số object.",
    }
    write_json(output / "livesign-source.json", source)
    write_json(root / "reports/stage0/datasets" / f"{project}-v{version}" / "source.json", source)
    return output
