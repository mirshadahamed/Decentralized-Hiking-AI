"""Long-distance trail graph from OSM stage relations (Pekoe Trail): ways joined end to end in member order."""
from src.data.stage_graph import stage_line


def _way(*pts):
    return {"type": "way", "geometry": [{"lon": x, "lat": y} for x, y in pts]}


def test_ways_are_flipped_to_join_end_to_end():
    # stored as A->B, C->B (reversed), C->D; the first way is also reversed relative to the second
    rel = {"members": [_way((1, 0), (0, 0)), _way((2, 0), (1, 0)), _way((2, 0), (3, 0)),
                       {"type": "node", "lon": 9, "lat": 9}]}
    assert stage_line(rel) == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_members_without_geometry_are_skipped():
    rel = {"members": [_way((0, 0), (1, 0)), {"type": "way"}, _way((1, 0), (2, 0))]}
    assert stage_line(rel) == [(0, 0), (1, 0), (2, 0)]
