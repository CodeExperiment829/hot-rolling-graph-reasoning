"""Compare three task-opening policies on fixed weighted conflict graphs."""
from collections import defaultdict
from functools import lru_cache
from itertools import combinations
import json
from statistics import mean

from publishing import ROOT, table


def costs(case):
    weights, edges = case["weights"], case["edges"]
    n = len(weights)

    @lru_cache(maxsize=None)
    def branch(uncovered):
        if not uncovered:
            return 0
        edge = min((edges[i] for i in uncovered), key=len)
        return min(weights[j] + branch(tuple(i for i in uncovered if j not in edges[i])) for j in edge)

    uncovered = set(range(len(edges)))
    exact = branch(tuple(sorted(uncovered)))
    greedy = 0
    while uncovered:
        j = min(range(n), key=lambda j: (-sum(j in edges[i] for i in uncovered) / weights[j], j))
        greedy += weights[j]
        uncovered = {i for i in uncovered if j not in edges[i]}
    masks = [sum(1 << j for j in edge) for edge in edges]
    feasible = (subset for size in range(n+1) for subset in combinations(range(n), size)
                if all(mask & sum(1 << j for j in subset) for mask in masks))
    first = next(feasible)
    cardinality = sum(weights[j] for j in first)
    check = min((sum(weights[j] for j in subset) for subset in feasible), default=cardinality)
    if min(check, cardinality) != exact:
        raise ValueError("Branch solution disagrees with exhaustive subset check")
    return exact, greedy, cardinality


def run():
    groups = defaultdict(list)
    for case in json.loads((ROOT / "Data/conflicts.json").read_text(encoding="utf-8")):
        groups[len(case["weights"])].append(costs(case))
    rows = []
    for n, records in sorted(groups.items()):
        scores = [f"{mean(col):.2f}" for col in zip(*records)]
        rows.append([n,len(records),*scores,sum(exact == greedy for exact,greedy,_ in records)])
    table("table_15", ["Tasks","Conflict graphs","Exact weighted hitting set","Greedy weighted hitting set",
          "Minimum-cardinality hitting set","Cases in which the greedy solution was optimal"], rows,
          caption="Cost of opening tasks for adjustment in small conflict graphs.")
    return {"families":[{"tasks":n,"cases":len(records),"mean_costs":[mean(col) for col in zip(*records)],
                         "greedy_optima":sum(a == b for a,b,_ in records)} for n,records in sorted(groups.items())]}

