"""Candidate alternatives on a supplied marked-trail graph.

This consumes reviewed, located observations. It does not infer trail blockage
from a litter detection, guess a GPS position, or invent an off-trail bypass.
"""
from __future__ import annotations

import heapq
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError('Timestamp must include timezone')
        return parsed
    except (TypeError, ValueError):
        return None


def suggest_alternative(graph, current_route, start, goal, observations, now=None):
    """Return a route candidate or a concrete missing-evidence state.

    Graph edges require explicit access permission and reviewed map geometry.
    Current observations require a reviewed edge match and bounded validity.
    Results remain candidates requiring a check of current local conditions.
    """
    now = now or datetime.now(timezone.utc)
    base = {'route': None, 'route_is_safety_certified': False,
            'visible_bypass': None, 'visible_bypass_status': 'reviewed_corridor_and_clearance_required'}

    def result(state, reason, **values):
        return dict(base, status=state, reason=reason, **values)

    if not graph or not graph.get('graph_id') or not graph.get('source_reference'):
        return result('insufficient_route_context', 'A located photo and a versioned marked-trail graph are required.')
    nodes = {n['id']: n for n in graph.get('nodes', [])}
    edges = {e['id']: e for e in graph.get('edges', [])}
    if any(not isinstance(key,str) or not key for key in [*nodes,*edges]):
        raise ValueError('Graph node and edge IDs must be nonempty strings')
    if len(nodes) != len(graph.get('nodes', [])) or len(edges) != len(graph.get('edges', [])):
        raise ValueError('Node and edge identifiers must be unique')
    if start not in nodes or goal not in nodes or start == goal or not current_route:
        return result('insufficient_route_context', 'Current position, destination and current marked route are required.')
    for node in nodes.values():
        lat, lon = node.get('lat'), node.get('lon')
        if not (isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and
                math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):
            raise ValueError('Graph nodes require finite latitude/longitude coordinates')
    for edge in edges.values():
        length = edge.get('length_m')
        if edge['from'] not in nodes or edge['to'] not in nodes:
            raise ValueError('Graph edge refers to missing node')
        if not isinstance(length,(int,float)) or not math.isfinite(length) or length <= 0:
            raise ValueError('Edge length must be finite and positive')
    cursor = start
    for edge_id in current_route:
        if edge_id not in edges:
            return result('insufficient_route_context', 'Current route is absent from this map version.')
        edge = edges[edge_id]
        if cursor == edge['from']: cursor = edge['to']
        elif cursor == edge['to'] and edge.get('bidirectional') is True: cursor = edge['from']
        else: return result('insufficient_route_context', 'Current route is not connected in its permitted direction.')
    if cursor != goal:
        return result('insufficient_route_context', 'Current route does not reach the requested destination.')

    active = {}; pending = []; unresolved_edges = set()
    for obs in observations:
        edge_id, hazard_id = obs.get('edge_id'), obs.get('hazard_id')
        reviewed_at, expires_at = timestamp(obs.get('reviewed_at')), timestamp(obs.get('expires_at'))
        reviewed = (obs.get('review_state') == 'reviewed' and bool(obs.get('reviewer_id')) and
                    isinstance(obs.get('observation_id'),str) and bool(obs['observation_id']) and
                    obs.get('edge_match_reviewed') is True and edge_id in edges and bool(hazard_id) and
                    isinstance(hazard_id,str) and
                    reviewed_at is not None and expires_at is not None and reviewed_at <= now < expires_at)
        if not reviewed:
            pending.append(obs.get('observation_id', 'unknown'))
            if edge_id in edges: unresolved_edges.add(edge_id)
            continue
        previous = active.get(hazard_id)
        if previous is None or reviewed_at > previous[0]: active[hazard_id] = (reviewed_at, obs)
    blocked = set(); evidence = []
    for _, obs in active.values():
        relation, blockage = obs.get('route_relation'), obs.get('blockage')
        if relation == 'beside_trail': continue
        if relation == 'on_trail' and blockage == 'blocked':
            blocked.add(obs['edge_id']); evidence.append(obs['observation_id'])
        elif relation != 'on_trail' or blockage not in ('clear',):
            unresolved_edges.add(obs['edge_id']); pending.append(obs['observation_id'])
    current = set(current_route)
    if not blocked.intersection(current):
        if pending:
            return result('review_required', 'Object detections need a located blockage/clearance review before rerouting.',
                          pending_observation_ids=pending)
        return result('no_confirmed_blockage', 'No current reviewed blockage affects the supplied route.')

    adjacency = {node: [] for node in nodes}
    excluded = blocked | unresolved_edges
    for edge_id, edge in edges.items():
        if edge_id in excluded or edge.get('permitted') is not True or edge.get('geometry_reviewed') is not True:
            continue
        adjacency[edge['from']].append((edge['to'],edge['length_m'],edge_id))
        if edge.get('bidirectional') is True:
            adjacency[edge['to']].append((edge['from'],edge['length_m'],edge_id))
    costs = {start: 0.0}; predecessors = {}; queue = [(0.0,start)]
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != costs[node]: continue
        if node == goal: break
        for neighbour, length, edge_id in adjacency[node]:
            candidate = cost + length
            if candidate < costs.get(neighbour,float('inf')):
                costs[neighbour] = candidate; predecessors[neighbour] = (node,edge_id)
                heapq.heappush(queue,(candidate,neighbour))
    if goal not in costs:
        return result('no_mapped_alternative', 'No permitted connected marked route avoids the known/pending obstructions.',
                      excluded_edge_ids=sorted(excluded), evidence_observation_ids=evidence)
    node_ids = [goal]; edge_ids = []; cursor = goal
    while cursor != start:
        cursor, edge_id = predecessors[cursor]; node_ids.append(cursor); edge_ids.append(edge_id)
    node_ids.reverse();edge_ids.reverse()
    route = {'graph_id':graph['graph_id'], 'source_reference':graph['source_reference'],
             'node_ids':node_ids, 'edge_ids':edge_ids, 'distance_m':costs[goal],
             'coordinates':[{'lat':nodes[n]['lat'],'lon':nodes[n]['lon']} for n in node_ids]}
    return result('candidate_marked_alternative', 'A mapped alternative is available; confirm current trail conditions.',
                  route=route, excluded_edge_ids=sorted(excluded), evidence_observation_ids=evidence,
                  requires_current_condition_check=True, pending_observation_ids=pending)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True,help='JSON request with graph, current_route, start, goal and observations')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();request=json.loads(args.input.read_text())
    response=suggest_alternative(request.get('graph'),request.get('current_route',[]),
                                 request.get('start'),request.get('goal'),request.get('observations',[]))
    text=json.dumps(response,indent=2,allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text,end='')


if __name__=='__main__':main()
