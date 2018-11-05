"""Traveling salesman problem optimizer.

Ported from the old Optimap stuff on gebweb.net.

Also see:
https://github.com/tzmartin/Google-Maps-TSP-Solver
"""

import itertools


def optimize(nodes, cost):
    """Optimized nodes according to cost.

    nodes[0] is always the start point.

    Args:
        nodes: List[str], will be modified in place
        cost: Function[str, str] -> float, cost from first to second
    """
    return _brute_force(nodes, cost)


def _brute_force(nodes, cost):
    for order in itertools.permutations(nodes[1:-1]):
        path = [nodes[0]]
        path.extend(order)
        path.append(nodes[-1])
        print path


def _dynamic(nodes, cost):
    pass


def _ant_colony(nodes, cost):
    pass


def _greedy(nodes, cost):
    pass


def _k_opt(nodes, cost, count):
    pass


_brute_force(['a', 'b', 'c', 'd', 'e', 'a'], ())
