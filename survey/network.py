"""HTTP có giới hạn, không ghi URL chứa token hay phản hồi bí mật vào log."""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from pathlib import Path

from .geometry import bbox_tiles
from .tiles import decode_points

GRAPH_ORIGIN = "https://graph.mapillary.com"
IMAGE_FIELDS = ",".join(
    (
        "id",
        "geometry",
        "computed_geometry",
        "captured_at",
        "sequence",
        "creator",
        "camera_type",
        "camera_parameters",
        "width",
        "height",
        "thumb_2048_url",
        "compass_angle",
        "computed_compass_angle",
    )
)


class SurveyError(Exception):
    """Lỗi an toàn để hiển thị; không chứa request, header hoặc body của dịch vụ."""


def canonical_id(value) -> str:
    identity = str(value)
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,30}", identity):
        raise SurveyError("ID Mapillary không phải chuỗi số hợp lệ.")
    return identity


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SurveyError("API chuyển hướng ngoài dự kiến. Yêu cầu đã dừng để giữ kín token.")


class HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise SurveyError("Từ chối chuyển hướng tải tệp sang URL không phải HTTPS.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Http:
    def __init__(
        self, attempts: int = 3, timeout_s: int = 60, sleep: Callable[[float], None] = time.sleep
    ):
        self.attempts = attempts
        self.timeout_s = timeout_s
        self.sleep = sleep
        self.opener = urllib.request.build_opener(NoRedirect())

    def read(
        self,
        url: str,
        *,
        token: str | None = None,
        body: bytes | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> bytes:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise SurveyError("Chỉ chấp nhận URL HTTPS không chứa tài khoản trong URL.")
        if token and (parsed.hostname != "graph.mapillary.com" or parsed.port not in (None, 443)):
            raise SurveyError("Token Mapillary chỉ được gửi tới Graph API chính thức.")
        headers = {"User-Agent": "LiveSign-survey/0.1 (academic data feasibility survey)"}
        if token:
            headers["Authorization"] = f"OAuth {token}"
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=body, headers=headers)
        for attempt in range(self.attempts):
            try:
                with self.opener.open(request, timeout=self.timeout_s) as response:
                    payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise SurveyError("Phản hồi vượt giới hạn dung lượng của yêu cầu.")
                return payload
            except urllib.error.HTTPError as error:
                status = error.code
                details = ""
                try:
                    api_error = json.loads(error.read(8192)).get("error", {})
                    code = api_error.get("code")
                    if isinstance(code, int):
                        details = f" Mã dịch vụ {code}."
                except (ValueError, OSError, AttributeError):
                    pass
                error.close()
                if status in (429, 500, 502, 503, 504) and attempt + 1 < self.attempts:
                    self.sleep(2**attempt)
                    continue
                raise SurveyError(
                    f"HTTP {status}.{details} Kiểm tra quyền truy cập hoặc giới hạn API."
                ) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt + 1 < self.attempts:
                    self.sleep(2**attempt)
                    continue
                raise SurveyError(
                    "Không kết nối được dịch vụ. Kiểm tra mạng rồi chạy lại."
                ) from None
        raise SurveyError("Yêu cầu không thực hiện được.")

    def json(self, url: str, **kwargs) -> dict:
        try:
            result = json.loads(self.read(url, **kwargs))
        except (ValueError, UnicodeError):
            raise SurveyError("Dịch vụ trả về JSON không hợp lệ.") from None
        if not isinstance(result, dict):
            raise SurveyError("Phản hồi API phải là object.")
        return result

    def download(self, url: str, path: Path, max_bytes: int = 2 * 1024**3) -> None:
        """Tải stream, không truyền Authorization qua redirect và không log signed URL."""
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise SurveyError("URL tải tệp cần HTTPS không có userinfo.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        request = urllib.request.Request(url, headers={"User-Agent": "LiveSign-survey/0.1"})
        try:
            opener = urllib.request.build_opener(HttpsRedirect())
            with (
                opener.open(request, timeout=self.timeout_s) as response,
                temporary.open("wb") as output,
            ):
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > max_bytes:
                        raise SurveyError("Tệp tải về vượt giới hạn dung lượng.")
                    output.write(block)
            temporary.replace(path)
        except (urllib.error.URLError, TimeoutError, OSError):
            temporary.unlink(missing_ok=True)
            raise SurveyError("Tải tệp không hoàn tất. Không ghi signed URL vào log.") from None


def safe_graph_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "graph.mapillary.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise SurveyError("Phân trang trỏ ra ngoài Graph API; đã dừng.")
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query)
        if key.lower() not in ("access_token", "token")
    ]
    return urllib.parse.urlunsplit(
        ("https", "graph.mapillary.com", parsed.path, urllib.parse.urlencode(query), "")
    )


class Mapillary:
    def __init__(self, token: str | None = None, http: Http | None = None):
        self.token = token or os.environ.get("MAPILLARY_TOKEN", "")
        if not self.token:
            raise SurveyError("Cần điền MAPILLARY_TOKEN trong .env trước khi khảo sát Mapillary.")
        self.http = http or Http()

    def pages(self, path: str, params: dict) -> Iterator[dict]:
        if not path.startswith("/") or path.startswith("//"):
            raise SurveyError("Đường dẫn Graph API không hợp lệ.")
        url = safe_graph_url(GRAPH_ORIGIN + path + "?" + urllib.parse.urlencode(params))
        visited = set()
        while url:
            if url in visited:
                raise SurveyError("API lặp trang. Chưa thể xác nhận danh sách đã đầy đủ.")
            visited.add(url)
            payload = self.http.json(url, token=self.token)
            if "error" in payload:
                raise SurveyError("Graph API từ chối yêu cầu. Kiểm tra token và quyền dữ liệu.")
            rows = payload.get("data")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise SurveyError("API không trả danh sách data hợp lệ.")
            yield from rows
            following = payload.get("paging", {}).get("next")
            url = safe_graph_url(following) if following else ""

    def images(self, bbox: list[float], years: list[int], step_degrees: float) -> list[dict]:
        by_id = {}
        for tile in bbox_tiles(bbox, step_degrees):
            params = {
                "bbox": ",".join(map(str, tile)),
                "fields": IMAGE_FIELDS,
                "start_captured_at": f"{min(years)}-01-01T00:00:00Z",
                "end_captured_at": f"{max(years) + 1}-01-01T00:00:00Z",
                "limit": 1000,
            }
            for image in self.pages("/images", params):
                if not image.get("id"):
                    raise SurveyError("Ảnh thiếu ID; không thể khử trùng chính xác.")
                by_id[canonical_id(image["id"])] = image
        return [by_id[key] for key in sorted(by_id)]

    def features(self, bbox: list[float], step_degrees: float) -> list[dict]:
        by_id = {}
        for tile in bbox_tiles(bbox, step_degrees):
            params = {
                "bbox": ",".join(map(str, tile)),
                "fields": "id,geometry,object_value,object_type",
                "limit": 1000,
            }
            for feature in self.pages("/map_features", params):
                if feature.get("object_type") not in ("traffic_sign", "trafficsign"):
                    continue
                if not feature.get("id"):
                    raise SurveyError("Feature thiếu ID.")
                by_id[canonical_id(feature["id"])] = feature
        return [by_id[key] for key in sorted(by_id)]

    def tile_entities(self, bbox: list[float], kind: str, cache: Path) -> list[dict]:
        """Dùng tile mức 14 có ID ảnh, creator_id và captured_at; không suy năm từ feature."""
        west, south, east, north = bbox
        z = 14

        def xy(longitude, latitude):
            return (
                int((longitude + 180) / 360 * 2**z),
                int((1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2 * 2**z),
            )

        minimum_x, minimum_y = xy(west, north)
        maximum_x, maximum_y = xy(east, south)
        layer_set = "mly1_public" if kind == "images" else "mly_map_feature_traffic_sign"
        by_id = {}
        for x in range(minimum_x, maximum_x + 1):
            for y in range(minimum_y, maximum_y + 1):
                path = cache / f"{layer_set}-{z}-{x}-{y}.mvt"
                if path.exists():
                    payload = path.read_bytes()
                else:
                    query = urllib.parse.urlencode({"access_token": self.token})
                    url = f"https://tiles.mapillary.com/maps/vtp/{layer_set}/2/{z}/{x}/{y}?{query}"
                    payload = self.http.read(url)
                    # Chỉ ghi tile sau khi giải mã thành công. Không ghi URL đã gắn token.
                    decode_points(payload, x, y, z)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                layers = decode_points(payload, x, y, z)
                points = (
                    layers.get("image", [])
                    if kind == "images"
                    else [item for rows in layers.values() for item in rows]
                )
                for feature in points:
                    longitude, latitude = feature["geometry"]["coordinates"]
                    if not west <= longitude <= east or not south <= latitude <= north:
                        continue
                    properties = feature["properties"]
                    if not properties.get("id"):
                        raise SurveyError("Tile có đối tượng thiếu ID.")
                    if kind == "images":
                        item = {
                            "id": canonical_id(properties["id"]),
                            "geometry": feature["geometry"],
                            "captured_at": properties["captured_at"],
                            "sequence": properties.get("sequence_id"),
                            "creator": {"id": str(properties["creator_id"])}
                            if properties.get("creator_id")
                            else None,
                            "camera_type": "spherical"
                            if properties.get("is_pano")
                            else "perspective",
                            "metadata_source": "coverage_vector_tile",
                        }
                    else:
                        item = {
                            "id": canonical_id(properties["id"]),
                            "geometry": feature["geometry"],
                            "object_value": properties.get("value", "unknown"),
                            "object_type": "traffic_sign",
                            "metadata_source": "traffic_sign_vector_tile",
                        }
                    by_id[item["id"]] = item
        return [by_id[key] for key in sorted(by_id)]


def fetch_osm(bbox: list[float], http: Http | None = None) -> dict:
    west, south, east, north = bbox
    query = f'[out:json][timeout:90];way["highway"]({south},{west},{north},{east});out body geom;'
    result = (http or Http(timeout_s=110)).json(
        "https://overpass-api.de/api/interpreter",
        body=urllib.parse.urlencode({"data": query}).encode("utf-8"),
    )
    if result.get("remark") or not isinstance(result.get("elements"), list):
        raise SurveyError("Overpass trả kết quả thiếu hoặc lỗi; chưa lưu thành dữ liệu hoàn chỉnh.")
    return result


def fetch_osm_map(bbox: list[float], cache: Path, http: Http | None = None) -> dict:
    """API OSM chính thức cho vùng nhỏ. Chia bbox để tránh giới hạn 50.000 nút."""
    transport = http or Http(attempts=2, timeout_s=45)
    nodes, ways, timestamps = {}, {}, set()
    for tile in bbox_tiles(bbox, 0.005):
        key = "-".join(f"{value:.6f}" for value in tile)
        path = cache / f"map-{key}.osm"
        if path.exists():
            payload = path.read_bytes()
        else:
            url = "https://api.openstreetmap.org/api/0.6/map?" + urllib.parse.urlencode(
                {"bbox": ",".join(map(str, tile))}
            )
            payload = transport.read(url)
            document = ET.fromstring(payload)
            if document.tag != "osm":
                raise SurveyError("API OSM không trả tài liệu osm hợp lệ.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        document = ET.fromstring(payload)
        metadata = document.find("meta")
        if metadata is not None and metadata.get("osm_base"):
            timestamps.add(metadata.get("osm_base"))
        for node in document.findall("node"):
            nodes[int(node.attrib["id"])] = {
                "lon": float(node.attrib["lon"]),
                "lat": float(node.attrib["lat"]),
            }
        for way in document.findall("way"):
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
            if "highway" in tags:
                ways[int(way.attrib["id"])] = {
                    "type": "way",
                    "id": int(way.attrib["id"]),
                    "nodes": [int(node.attrib["ref"]) for node in way.findall("nd")],
                    "tags": tags,
                }
    result = []
    for way in ways.values():
        try:
            way["geometry"] = [nodes[identity] for identity in way["nodes"]]
        except KeyError:
            raise SurveyError(
                "API OSM còn way thiếu nút. Chưa thể dựng tuyến có thể kiểm lại."
            ) from None
        result.append(way)
    return {
        "version": 0.6,
        "generator": "LiveSign OSM map API reader",
        "osm3s": {
            "timestamp_osm_base": sorted(timestamps),
            "copyright": "© OpenStreetMap contributors; ODbL",
        },
        "elements": sorted(result, key=lambda value: value["id"]),
        "retrieval_source": "https://api.openstreetmap.org/api/0.6/map",
    }
