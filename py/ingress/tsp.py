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
    print 'optimizing %d nodes with initial path cost of %.1f' % (
        len(nodes), _path_cost(nodes, cost))
    # return _brute_force(nodes, cost)
    # return _greedy(nodes, cost)
    tmp = _greedy(nodes, cost)
    return _k_opt(tmp[1], cost)


def _brute_force(nodes, cost):
    best_cost = sys.maxint
    best_path = None
    for order in itertools.permutations(nodes[1:-1]):
        path = [nodes[0]]
        path.extend(order)
        path.append(nodes[-1])
        path_cost = _path_cost(path, cost)

        if path_cost < best_cost:
            best_cost = path_cost
            best_path = path[:]

    return best_cost, best_path


def _greedy(nodes, cost):
    nodes_to_visit = set(nodes[1:-1])
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

    return _path_cost(path, cost), path


def _ant_colony(nodes, cost):
    pass


def _k_opt(nodes, cost):
    node_count = len(nodes)
    best_cost = _path_cost(nodes, cost)
    best_path = nodes[:]
    first = best_path[0]
    last = best_path[-1]
    improved = True
    k_opt = 1
    while improved:
        improved = False
        sub_path = best_path[1:-1]
        for swaps in _swappables(node_count, k_opt):
            segments = list()
            for start, end in zip(swaps, swaps[1:]):
                segments.append(sub_path[start:end])
            for combo in itertools.permutations(segments):
                new_path = [first] + list(itertools.chain(*combo)) + [last]
                new_cost = _path_cost(new_path, cost)
                if new_cost < best_cost:
                    improved = True
                    best_cost = new_cost
                    best_path = new_path[:]
                    sub_path = best_path[1:-1]
        if not improved and k_opt < 3:
            improved = True
            k_opt += 1

    return best_cost, best_path


def _path_cost(path, cost):
    path_cost = 0
    for start, end in zip(path, path[1:]):
        path_cost += cost(start, end)
    return path_cost


def _swappables(node_count, sw_count):
    swaps = itertools.combinations(range(node_count), sw_count)
    for temp_swap in swaps:
        swap = [None]
        swap.extend(temp_swap)
        usable = True
        for first, second in zip(swap, swap[1:]):
            if second <= first:
                usable = False
        if usable:
            swap.append(None)
            yield swap
