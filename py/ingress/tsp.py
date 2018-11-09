"""Traveling salesman problem optimizer.

Ported from the old Optimap stuff on gebweb.net.

Also see:
https://github.com/tzmartin/Google-Maps-TSP-Solver
"""

import itertools
import sys


def optimize(nodes, cost):
    """Optimized nodes according to cost.

    nodes[0] is always the start point.

    Args:
        nodes: List[str], will be modified in place
        cost: Function[str, str] -> float, cost from first to second
    """
    print 'optimizing %d nodes' % len(nodes)
    # return _brute_force(nodes, cost)
    return _greedy(nodes, cost)


def _brute_force(nodes, cost):
    best_cost = sys.maxint
    best_path = None
    for order in itertools.permutations(nodes[1:-1]):
        path = [nodes[0]]
        path.extend(order)
        path.append(nodes[-1])
        path_cost = 0
        for start, end in zip(path, path[1:]):
            path_cost += cost(start, end)

        if path_cost < best_cost:
            best_cost = path_cost
            best_path = path[:]

    return best_cost, best_path


def _greedy(nodes, cost):
    nodes_to_visit = set(nodes[1:])
    start = nodes[0]
    path = [start]
    while nodes_to_visit:
        costs = set()
        for end in nodes_to_visit:
            this_cost = cost(start, end)
            costs.add((this_cost, end))
        end = min(costs)[1]
        path.append(end)
        nodes_to_visit.discard(end)
        start = end
    path.append(nodes[0])

    path_cost = 0
    for start, end in zip(path, path[1:]):
        path_cost += cost(start, end)
    return path_cost, path


def _ant_colony(nodes, cost):
    pass


def _k_opt(nodes, cost, count):
    pass
