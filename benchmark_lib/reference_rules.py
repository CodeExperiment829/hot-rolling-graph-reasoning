"""Scheduling, retrieval, and sequencing on released benchmark records."""
import collections
from bisect import insort
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1] / "Data/benchmarks"


def read_fjsp(raw):
    rows = [
        list(map(int, line.split()))
        for line in raw.decode().splitlines()
        if line.strip()
    ]
    count, n_machines = rows[0][:2]
    jobs = []
    for row in rows[1:]:
        it = iter(row)
        ops = []
        for _ in range(next(it)):
            choices = [(next(it), next(it)) for _ in range(next(it))]
            assert all(0 <= m < n_machines and d > 0 for m, d in choices)
            ops.append(choices)
        assert list(it) == []
        jobs.append(ops)
    assert len(jobs) == count
    return jobs


def list_schedule(jobs, rule):
    ends = [0] * len(jobs)
    index = [0] * len(jobs)
    busy = collections.defaultdict(int)
    entries = []
    for _ in range(sum(map(len, jobs))):
        candidates = []
        for j, ops in enumerate(jobs):
            k = index[j]
            if k == len(ops):
                continue
            for m, d in ops[k]:
                start = max(ends[j], busy[m])
                end = start + d
                key = (end, start, j, m) if rule == "ECT" else (ends[j], j, end, m)
                candidates.append((key, (j, k, m, start, end)))
        _, entry = min(candidates)
        j, k, m, start, end = entry
        entries.append(entry)
        ends[j] = busy[m] = end
        index[j] += 1
    by_job = collections.defaultdict(list)
    by_machine = collections.defaultdict(list)
    for j, k, m, start, end in entries:
        assert (m, end - start) in jobs[j][k]
        by_job[j].append((k, start, end))
        by_machine[m].append((start, end))
    for j, ops in enumerate(jobs):
        sequence = sorted(by_job[j])
        assert [x[0] for x in sequence] == list(range(len(ops)))
        assert all(x[2] <= y[1] for x, y in zip(sequence, sequence[1:]))
    for intervals in by_machine.values():
        ordered = sorted(intervals)
        assert all(x[1] <= y[0] for x, y in zip(ordered, ordered[1:]))
    return max(ends)


def taskbench():
    tools = json.loads((ROOT / "tools.json").read_text(encoding="utf8"))["nodes"]
    names = [t["id"] for t in tools]
    inp = [set(s.lower() for s in t["input-type"]) for t in tools]
    out = [set(s.lower() for s in t["output-type"]) for t in tools]
    vector = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    catalog = vector.fit_transform(t["id"] + " " + t["desc"] for t in tools)
    raw = [
        json.loads(s)
        for s in (ROOT / "taskbench.jsonl").read_text(encoding="utf8").splitlines()
        if s.strip()
    ]
    matrix = (vector.transform(r["instruction"] for r in raw) @ catalog.T).toarray()
    counts = collections.Counter()
    shapes = collections.Counter()
    excluded = []
    for r, scores in zip(raw, matrix):
        selected = sorted(range(len(names)), key=lambda i: (-scores[i], names[i]))
        cut = max(0.08, 0.6 * scores[selected[0]])
        selected = [i for i in selected if scores[i] >= cut][:4]
        pred_n = {names[i] for i in selected}
        pred_e = {
            (names[i], names[j])
            for i, j in zip(selected, selected[1:])
            if out[i] & inp[j]
        }
        gold_nodes = json.loads(r["tool_nodes"])
        if isinstance(gold_nodes, dict):
            gold_nodes = [gold_nodes]
        edges = json.loads(r["tool_links"])
        if not all(isinstance(x.get("task"), str) for x in gold_nodes) or not all(
            isinstance(x.get("source"), str) and isinstance(x.get("target"), str)
            for x in edges
        ):
            excluded.append(r["id"])
            continue
        gold_n = {x["task"] for x in gold_nodes}
        gold_e = {(x["source"], x["target"]) for x in edges}
        for tag, pred, gold in (("node", pred_n, gold_n), ("edge", pred_e, gold_e)):
            counts[tag + "_tp"] += len(pred & gold)
            counts[tag + "_pred"] += len(pred)
            counts[tag + "_gold"] += len(gold)
        counts["exact"] += gold_n == pred_n and gold_e == pred_e
        shapes[r["type"]] += 1
    results = dict(
        raw=len(raw),
        records=len(raw) - len(excluded),
        excluded=len(excluded),
        catalog=len(names),
        shapes=dict(shapes),
        **counts
    )
    for tag in ("node", "edge"):
        results[tag + "_f1"] = (
            2 * counts[tag + "_tp"] / (counts[tag + "_pred"] + counts[tag + "_gold"])
        )
    return results


def galvanizing():
    # The published example ordering is evaluated on the same cost matrix.
    matrix = [
        [int(v) for v in row.split(";")]
        for row in (ROOT / "cgl_17.txt").read_text().splitlines()
    ]
    n = len(matrix)

    def cost(path):
        assert sorted(path) == list(range(n))
        arcs = [matrix[u][v] for u, v in zip(path, path[1:])]
        assert all(x >= 0 for x in arcs)
        return sum(arcs)

    published = [2, 0, 1, 3, 4, 5, 6, 7, 16, 11, 15, 10, 8, 12, 14, 13, 9]
    layer = {(1 << i, i): (0, (i,)) for i in range(n)}
    for _ in range(n - 1):
        new = {}
        for (mask, last), (old, path) in layer.items():
            for nxt, arc in enumerate(matrix[last]):
                if arc < 0 or mask & (1 << nxt):
                    continue
                key = (mask | (1 << nxt), nxt)
                candidate = (old + arc, path + (nxt,))
                if key not in new or candidate < new[key]:
                    new[key] = candidate
        layer = new
    optimum, path = min(layer.values())
    assert optimum == cost(path)
    greedy_paths = []
    for start in range(n):
        route = [start]
        while len(route) < n:
            feasible = [
                (x, j)
                for j, x in enumerate(matrix[route[-1]])
                if x >= 0 and j not in route
            ]
            if not feasible:
                break
            route.append(min(feasible)[1])
        if len(route) == n:
            greedy_paths.append((cost(route), route))
    return dict(
        instance="cgl_17",
        n=n,
        allowed_arcs=sum(x >= 0 for row in matrix for x in row),
        catalog_order_cost=cost(range(n)),
        published_example_cost=cost(published),
        multistart_greedy_complete=len(greedy_paths),
        best_greedy_cost=min(cost for cost, _ in greedy_paths)
        if greedy_paths
        else None,
        exact_optimum=optimum,
    )


def dispatch(jobs, policy):
    cal = collections.defaultdict(list)
    pos = [0] * len(jobs)
    ready = [0] * len(jobs)
    tail = [
        [sum(min(d for m, d in opts) for opts in job[k:]) for k in range(len(job))]
        for job in jobs
    ]
    plan = []
    for _ in range(sum(map(len, jobs))):
        choices = []
        for j, job in enumerate(jobs):
            k = pos[j]
            if k == len(job):
                continue
            for m, d in job[k]:
                begin = ready[j]
                for a, b in cal[m]:
                    if begin + d <= a:
                        break
                    begin = max(b, begin)
                finish = begin + d
                orders = [
                    (ready[j], j, finish),
                    (begin, -tail[j][k], finish),
                    (finish, -tail[j][k], begin),
                ]
                choices.append((orders[policy], j, k, m, begin, finish))
        _, j, k, m, a, b = min(choices)
        insort(cal[m], (a, b))
        pos[j] += 1
        ready[j] = b
        plan.append((j, k, m, a, b))
    last = {}
    mc = collections.defaultdict(list)
    for j, k, m, a, b in plan:
        assert (m, b - a) in jobs[j][k] and a >= last.get((j, k - 1), 0)
        last[j, k] = b
        mc[m].append((a, b))
    assert all(
        all(t[1] <= u[0] for t, u in zip(sorted(tasks), sorted(tasks)[1:]))
        for tasks in mc.values()
    )
    return max(ready)
