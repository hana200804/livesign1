"""Hình học khảo sát đường. Không định vị hay gộp biển báo."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable

EARTH_RADIUS_M = 6_371_008.8
Point = tuple[float, float]  # longitude, latitude


def point(value: Iterable[float]) -> Point:
    longitude, latitude = map(float, value)
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("Tọa độ phải hữu hạn.")
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("Tọa độ ngoài miền WGS84.")
    return longitude, latitude


def distance_m(first: Point, second: Point) -> float:
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    value = math.sin((lat2 - lat1) / 2) ** 2
    value += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1, math.sqrt(value)))


def segment_distance_m(value: Point, start: Point, end: Point) -> float:
    reference = math.radians(value[1])
    scale_x = EARTH_RADIUS_M * math.cos(reference) * math.pi / 180
    scale_y = EARTH_RADIUS_M * math.pi / 180
    ax, ay = (start[0] - value[0]) * scale_x, (start[1] - value[1]) * scale_y
    bx, by = (end[0] - value[0]) * scale_x, (end[1] - value[1]) * scale_y
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(ax, ay)
    fraction = max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + fraction * dx, ay + fraction * dy)


def polyline_distance_m(value: Point, line: list[Point]) -> float:
    if len(line) < 2:
        raise ValueError("Tuyến cần ít nhất hai điểm OSM.")
    return min(segment_distance_m(value, start, end) for start, end in zip(line, line[1:]))


def sample_line(line: list[Point], step_m: float) -> list[tuple[Point, float]]:
    """Lấy trung điểm mỗi đoạn ≤step, trọng số bằng chiều dài thật của đoạn."""
    if step_m <= 0:
        raise ValueError("Bước lấy mẫu phải > 0 m.")
    samples = []
    for start, end in zip(line, line[1:]):
        length = distance_m(start, end)
        if length == 0:
            continue
        count = max(1, math.ceil(length / step_m))
        for index in range(count):
            fraction = (index + 0.5) / count
            middle = (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
            samples.append((middle, length / count))
    return samples


class PointIndex:
    """Chỉ mục ảnh theo ô mét để đo độ phủ; không dùng ô để dựng tuyến."""

    def __init__(self, entries: list[tuple[Point, dict]], cell_m: float = 50):
        if cell_m <= 0:
            raise ValueError("Kích thước ô phải > 0 m.")
        self.cell_m = cell_m
        self.cells: dict[tuple[int, int], list[tuple[Point, dict]]] = defaultdict(list)
        self.reference_lat = entries[0][0][1] if entries else 21.0
        self.scale_x = EARTH_RADIUS_M * math.cos(math.radians(self.reference_lat)) * math.pi / 180
        self.scale_y = EARTH_RADIUS_M * math.pi / 180
        for location, data in entries:
            self.cells[self._cell(location)].append((location, data))

    def _cell(self, location: Point) -> tuple[int, int]:
        return (
            math.floor(location[0] * self.scale_x / self.cell_m),
            math.floor(location[1] * self.scale_y / self.cell_m),
        )

    def within(self, location: Point, radius_m: float) -> list[dict]:
        if radius_m < 0:
            raise ValueError("Bán kính phải ≥ 0 m.")
        x, y = self._cell(location)
        # Thêm một ô dự phòng cho sai khác phép chiếu trên vùng mẫu Hà Nội.
        reach = math.ceil(radius_m / self.cell_m) + 1
        return [
            data
            for dx in range(-reach, reach + 1)
            for dy in range(-reach, reach + 1)
            for candidate, data in self.cells.get((x + dx, y + dy), [])
            if distance_m(location, candidate) <= radius_m
        ]

    def any_within(self, location: Point, radius_m: float) -> bool:
        if radius_m < 0:
            raise ValueError("Bán kính phải ≥ 0 m.")
        x, y = self._cell(location)
        reach = math.ceil(radius_m / self.cell_m) + 1
        return any(
            distance_m(location, candidate) <= radius_m
            for dx in range(-reach, reach + 1)
            for dy in range(-reach, reach + 1)
            for candidate, _ in self.cells.get((x + dx, y + dy), [])
        )


def bbox_tiles(bbox: list[float], step_degrees: float) -> list[list[float]]:
    west, south, east, north = bbox
    point((west, south))
    point((east, north))
    if west >= east or south >= north or step_degrees <= 0:
        raise ValueError("BBox hoặc bước chia không hợp lệ.")
    columns = math.ceil((east - west) / step_degrees)
    rows = math.ceil((north - south) / step_degrees)
    return [
        [
            west + x * step_degrees,
            south + y * step_degrees,
            min(east, west + (x + 1) * step_degrees),
            min(north, south + (y + 1) * step_degrees),
        ]
        for x in range(columns)
        for y in range(rows)
    ]


def clip_segment(start: Point, end: Point, bbox: list[float]) -> list[Point] | None:
    """Liang–Barsky: giữ phần đường thật nằm trong bbox, không tính cả way ngoài vùng."""
    west, south, east, north = bbox
    dx, dy = end[0] - start[0], end[1] - start[1]
    lower, upper = 0.0, 1.0
    for direction, offset in (
        (-dx, start[0] - west),
        (dx, east - start[0]),
        (-dy, start[1] - south),
        (dy, north - start[1]),
    ):
        if direction == 0:
            if offset < 0:
                return None
            continue
        fraction = offset / direction
        if direction < 0:
            lower = max(lower, fraction)
        else:
            upper = min(upper, fraction)
        if lower >= upper:
            return None
    return [
        (start[0] + lower * dx, start[1] + lower * dy),
        (start[0] + upper * dx, start[1] + upper * dy),
    ]


def padded_bbox(bbox: list[float], padding_m: float) -> list[float]:
    west, south, east, north = bbox
    latitude = (south + north) / 2
    latitude_delta = math.degrees(padding_m / EARTH_RADIUS_M)
    longitude_delta = latitude_delta / math.cos(math.radians(latitude))
    return [
        west - longitude_delta,
        south - latitude_delta,
        east + longitude_delta,
        north + latitude_delta,
    ]
