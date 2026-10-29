"""Dựng tuyến từ nút/cạnh đường OSM thật, tôn trọng đường một chiều cơ bản."""

from __future__ import annotations

import heapq
from collections import defaultdict

from .geometry import Point, clip_segment, distance_m, point

DRIVABLE = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
}


def driveable_ways(document: dict) -> list[dict]:
    result = []
    for way in document.get("elements", []):
        tags = way.get("tags", {})
        if way.get("type") != "way" or tags.get("highway") not in DRIVABLE:
            continue
        if tags.get("area") == "yes" or tags.get("motor_vehicle") in ("no", "private"):
            continue
        if tags.get("access") in ("no", "private") and tags.get("motor_vehicle") not in (
            "yes",
            "permissive",
        ):
            continue
        if len(way.get("geometry", [])) != len(way.get("nodes", [])):
            raise ValueError("OSM thiếu hình học nút; cần truy vấn out body geom.")
        if len(way.get("nodes", [])) >= 2:
            result.append(way)
    return result


def road_lines(document: dict, bbox: list[float] | None = None) -> list[list[Point]]:
    # Cạnh chia sẻ giữa các way chỉ tính một lần trong mẫu số chiều dài.
    segments = {}
    for way in driveable_ways(document):
        for index in range(len(way["nodes"]) - 1):
            key = tuple(sorted(way["nodes"][index : index + 2]))
            segments[key] = [
                point((item["lon"], item["lat"])) for item in way["geometry"][index : index + 2]
            ]
    if bbox is None:
        return [segments[key] for key in sorted(segments)]
    clipped = [clip_segment(segments[key][0], segments[key][1], bbox) for key in sorted(segments)]
    return [segment for segment in clipped if segment is not None]


def graph(document: dict) -> tuple[dict[int, Point], dict[int, list[tuple[int, float, int]]]]:
    nodes = {}
    edges = defaultdict(list)
    for way in driveable_ways(document):
        tags = way.get("tags", {})
        one_way = tags.get("oneway")
        if one_way is None and tags.get("junction") == "roundabout":
            one_way = "yes"
        for node_id, coordinate in zip(way["nodes"], way["geometry"]):
            nodes[node_id] = point((coordinate["lon"], coordinate["lat"]))
        for first, second in zip(way["nodes"], way["nodes"][1:]):
            length = distance_m(nodes[first], nodes[second])
            if one_way != "-1":
                edges[first].append((second, length, way["id"]))
            if one_way not in ("yes", "1", "true"):
                edges[second].append((first, length, way["id"]))
    return nodes, dict(edges)


def shortest_path(edges: dict, start: int, end: int) -> tuple[list[int], list[int]]:
    queue = [(0.0, start)]
    distances = {start: 0.0}
    previous = {}
    while queue:
        total, current = heapq.heappop(queue)
        if total != distances.get(current):
            continue
        if current == end:
            route, ways = [end], []
            while route[-1] != start:
                parent, way_id = previous[route[-1]]
                route.append(parent)
                ways.append(way_id)
            return route[::-1], ways[::-1]
        for neighbor, length, way_id in edges.get(current, []):
            proposed = total + length
            if proposed < distances.get(neighbor, float("inf")):
                distances[neighbor] = proposed
                previous[neighbor] = current, way_id
                heapq.heappush(queue, (proposed, neighbor))
    raise ValueError("Không có đường OSM liên thông theo hướng giữa các điểm neo.")


def make_route(
    document: dict, seed: dict, max_snap_m: float, target_length_m: float | None = None
) -> dict:
    nodes, edges = graph(document)
    if not nodes:
        raise ValueError("Không có đường OSM chạy xe được trong vùng.")
    anchors = [point(value) for value in seed["anchors"]]
    if len(anchors) < 2:
        raise ValueError("Cần ít nhất hai điểm neo.")
    snapped = []
    snap_distances = []
    for anchor in anchors:
        nearest = min(nodes, key=lambda node: distance_m(anchor, nodes[node]))
        offset = distance_m(anchor, nodes[nearest])
        if offset > max_snap_m:
            raise ValueError(f"Điểm neo cách nút OSM {offset:.1f} m, vượt {max_snap_m:.1f} m.")
        snapped.append(nearest)
        snap_distances.append(round(offset, 3))
    node_path, way_path = [], []
    for start, end in zip(snapped, snapped[1:]):
        section, ways = shortest_path(edges, start, end)
        node_path.extend(section if not node_path else section[1:])
        way_path.extend(ways)
    if len(node_path) < 2:
        raise ValueError("Các điểm neo trùng nút; tuyến chưa có chiều dài.")
    coordinates = [nodes[node_id] for node_id in node_path]
    length = sum(distance_m(start, end) for start, end in zip(coordinates, coordinates[1:]))
    anchor_path_length = length
    if target_length_m is not None and length > target_length_m:
        if target_length_m <= 0:
            raise ValueError("Chiều dài mục tiêu phải > 0 m.")
        cumulative = [0.0]
        for start, end in zip(coordinates, coordinates[1:]):
            cumulative.append(cumulative[-1] + distance_m(start, end))
        end_index = min(
            range(1, len(cumulative)), key=lambda index: abs(cumulative[index] - target_length_m)
        )
        node_path, way_path = node_path[: end_index + 1], way_path[:end_index]
        coordinates = coordinates[: end_index + 1]
        length = cumulative[end_index]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "id": seed["id"],
            "name": seed["name"],
            "region": seed["region"],
            "status": "candidate",
            "length_m": round(length, 3),
            "anchor_path_length_m": round(anchor_path_length, 3),
            "trimmed_at_osm_node": length != anchor_path_length,
            "osm_node_ids": node_path,
            "osm_way_ids_per_edge": way_path,
            "anchor_snap_distances_m": snap_distances,
            "attribution": "© OpenStreetMap contributors",
            "limitations": "Chưa kiểm hạn chế rẽ, thời gian và hạn chế từng loại xe.",
        },
    }
