import pytest

from survey.geometry import PointIndex, bbox_tiles, clip_segment, distance_m, sample_line
from survey.osm import graph, make_route, road_lines, shortest_path


def way(identity, nodes, coordinates, **tags):
    return {
        "type": "way",
        "id": identity,
        "nodes": nodes,
        "geometry": [{"lon": lon, "lat": lat} for lon, lat in coordinates],
        "tags": {"highway": "residential", **tags},
    }


def document():
    return {
        "elements": [
            way(7, [1, 2, 3], [(105.85, 21.03), (105.851, 21.03), (105.852, 21.03)], oneway="yes")
        ]
    }


def test_route_reuses_actual_osm_nodes_and_respects_one_way():
    nodes, edges = graph(document())
    assert shortest_path(edges, 1, 3) == ([1, 2, 3], [7, 7])
    with pytest.raises(ValueError, match="Không có đường"):
        shortest_path(edges, 3, 1)
    seed = {"id": "a", "name": "Tuyến", "region": "hoan_kiem", "anchors": [nodes[1], nodes[3]]}
    result = make_route(document(), seed, 30)
    assert result["geometry"]["coordinates"] == [nodes[1], nodes[2], nodes[3]]
    assert result["properties"]["status"] == "candidate"


def test_snap_far_from_road_stops_instead_of_drawing_straight_line():
    seed = {
        "id": "a",
        "name": "Tuyến",
        "region": "hoan_kiem",
        "anchors": [[105.7, 21.03], [105.852, 21.03]],
    }
    with pytest.raises(ValueError, match="vượt"):
        make_route(document(), seed, 30)


def test_coverage_clips_whole_osm_ways_to_survey_boundary():
    lines = road_lines(document(), [105.8505, 21.02, 105.8515, 21.04])
    length = sum(distance_m(*line) for line in lines)
    assert length == pytest.approx(distance_m((105.8505, 21.03), (105.8515, 21.03)), rel=1e-6)
    assert clip_segment((1, 2), (3, 2), [1.5, 1, 2.5, 3]) == [(1.5, 2.0), (2.5, 2.0)]
    assert clip_segment((1, 4), (3, 4), [1.5, 1, 2.5, 3]) is None


def test_weighted_samples_preserve_road_length():
    line = [(105.85, 21.03), (105.851, 21.03)]
    assert sum(weight for _, weight in sample_line(line, 10)) == pytest.approx(distance_m(*line))
    assert all(weight <= 10 for _, weight in sample_line(line, 10))


def test_point_index_filters_by_metres_not_grid_adjacency():
    index = PointIndex([((105.85, 21.03), {"id": "close"}), ((105.86, 21.03), {"id": "far"})])
    assert index.within((105.85, 21.03), 30) == [{"id": "close"}]


def test_duplicate_edges_are_counted_once():
    source = document()
    source["elements"].append(way(8, [1, 2], [(105.85, 21.03), (105.851, 21.03)]))
    assert len(road_lines(source)) == 2


def test_bbox_tile_partition_has_no_area_gaps():
    tiles = bbox_tiles([105.84, 21.02, 105.853, 21.033], 0.005)
    assert len(tiles) == 9
    assert sum(
        (east - west) * (north - south) for west, south, east, north in tiles
    ) == pytest.approx(0.013**2)
