"""Cell scheduling and independent verification against Tables 3 through 6 of the benchmark."""
from collections import defaultdict
from pathlib import Path
import itertools
import json
import re

_data = Path(__file__).resolve().parents[1] / "Data/benchmarks/cell_tables.json"
_tables = json.loads(_data.read_text(encoding="utf8"))


def table(index):
    return _tables[str(index)]


def integer(s):
    return int(re.search(r"[0-9]+", s)[0])


cells = table(3)
groups = table(4)
times = table(5)
transport = {}
setup = {}
for i in range(1, 7):
    for j in range(1, 7):
        transport[i, j] = 0 if i == j else int(times[i + 1][j])
for i in range(1, 8):
    for j in range(1, 8):
        setup[i, j] = 0 if i == j else int(times[i + 1][j + 7])
jobs = {}
for r in table(6):
    if len(r) > 1 and r[0] == "" and re.fullmatch(r"P\d+", r[1]):
        header = [integer(p) for p in r[1:] if re.fullmatch(r"P\d+", p)]
    elif re.fullmatch(r"M[0-9]+", r[0]):
        for p, val in zip(header, r[1:]):
            if val[0].isdigit():
                jobs.setdefault(p, {}).setdefault("dur", {})[integer(r[0])] = integer(
                    val
                )
    elif r[0].startswith("Route (Except"):
        for p, val in zip(header, r[1:]):
            jobs.setdefault(p, {})["route"] = list(map(int, re.findall(r"\d+", val)))
    elif r[0] == "Due dates":
        for p, val in zip(header, r[1:]):
            if re.search(r"\d", val):
                jobs.setdefault(p, {})["due"] = integer(val)


def load(i):
    machines = {}
    # Parallel copies of a machine retain the original machine class and cell.
    for c, rawc in enumerate(cells[i + 1][1:], 1):
        for m, count in re.findall(r"M(\d+)(?:\((\d+)\))?", rawc):
            for n in range(int(count or 1)):
                machines[(int(m), n + 1)] = c
    parts = {}
    for f, x in enumerate(groups[i + 1][1:], 1):
        for pnum in re.findall(r"P\s*(\d+)", x):
            p = int(pnum)
            rec = jobs[p]
            rout = [6, 3, 6] if i in [4, 7] and p == 11 else rec["route"]
            parts[p] = dict(
                f=f,
                route=rout,
                dur=rec["dur"],
                due=8 if i == 2 and p == 23 else rec["due"],
            )
            assert all(any(m == k[0] for k in machines) for m in rout), (
                i,
                p,
                rout,
                machines,
            )
    return machines, parts


def run(machines, parts, priority):
    hist = defaultdict(list)
    completed = defaultdict(list)
    remaining = sum(len(p["route"]) for p in parts.values())
    out = []
    while len(out) < remaining:
        options = []
        for j, p in parts.items():
            idx = len(completed[j])
            if idx >= len(p["route"]):
                continue
            c = p["route"][idx]
            dur = p["dur"][c]
            for m, cell in machines.items():
                if m[0] != c:
                    continue
                prior = completed[j][-1] if idx else None
                transfer = transport[machines[tuple(prior["m"])], cell] if prior else 0
                previous = hist[m][-1] if hist[m] else None
                change = setup[parts[previous["j"]]["f"], p["f"]] if previous else 0
                ready = prior["end"] + transfer if prior else 0
                available = previous["end"] + change if previous else 0
                start = max(ready, available)
                score = (
                    (p["due"], start + dur, j, m)
                    if priority == "EDD"
                    else (start + dur, p["due"], j, m)
                )
                options.append(
                    (score, dict(j=j, i=idx, m=list(m), start=start, end=start + dur))
                )
        rec = min(options, key=lambda x: x[0])[1]
        out.append(rec)
        hist[tuple(rec["m"])].append(rec)
        completed[rec["j"]].append(rec)
    return out


def independently_check(ms, ps, ops):
    issues = []
    late = 0
    transit_count = 0
    setup_count = 0
    for j, p in ps.items():
        q = sorted((x for x in ops if x["j"] == j), key=lambda x: x["i"])
        assert len(q) == len(p["route"])
        for k, x in enumerate(q):
            m = tuple(x["m"])
            need = p["route"][k]
            if m not in ms or m[0] != need or x["end"] - x["start"] != p["dur"][need]:
                issues.append("assignment")
            if k:
                prev = q[k - 1]
                cell0 = ms[tuple(prev["m"])]
                change = transport[cell0, ms[m]]
                transit_count += int(change > 0)
                if x["start"] - prev["end"] < change:
                    issues.append("transfer")
        late += max(0, q[-1]["end"] - p["due"])
    for m in ms:
        s = sorted((x for x in ops if tuple(x["m"]) == m), key=lambda x: x["start"])
        for a, b in zip(s, s[1:]):
            move = setup[ps[a["j"]]["f"], ps[b["j"]]["f"]]
            setup_count += int(move > 0)
            if b["start"] - a["end"] < move:
                issues.append("setup")
    return dict(
        ok=not issues,
        issues=issues,
        makespan=max(x["end"] for x in ops),
        total_tardiness=late,
        transport_moves=transit_count,
        family_changes=setup_count,
    )


def evaluate_dispatch():
    raw_results = []
    for i in range(1, 13):
        machines, parts = load(i)
        for k in ["EDD", "earliest_finish"]:
            schedule = run(machines, parts, k)
            out = independently_check(machines, parts, schedule)
            assert out["ok"]
            raw_results.append(
                dict(
                    instance=i,
                    method=k,
                    n_jobs=len(parts),
                    n_machines=len(machines),
                    n_ops=len(schedule),
                    result=out,
                    schedule=schedule,
                )
            )
    stats = {}
    for m in ["EDD", "earliest_finish"]:
        sub = [a for a in raw_results if a["method"] == m]
        stats[m] = dict(
            n=len(sub),
            success=sum(x["result"]["ok"] for x in sub),
            total_ops=sum(x["n_ops"] for x in sub),
            avg_makespan=sum(x["result"]["makespan"] for x in sub) / len(sub),
            avg_tardiness=sum(x["result"]["total_tardiness"] for x in sub) / len(sub),
            total_moves=sum(x["result"]["transport_moves"] for x in sub),
            total_family_changes=sum(x["result"]["family_changes"] for x in sub),
        )
    return stats


def alternatives(ops, n):
    assert n in [1, 2]
    plans = set()
    for perm in itertools.permutations(ops):
        if n == 1:
            plans.add((perm,))
        else:
            for split in range(len(perm) + 1):
                a = perm[:split]
                b = perm[split:]
                plans.add(tuple(sorted((a, b))))
    return sorted(plans)


def exact_first_instance():
    machines, parts = load(1)

    def solve_component(job_ids):
        bytype = defaultdict(list)
        duration = {}
        for j in job_ids:
            for k, t in enumerate(parts[j]["route"]):
                bytype[t].append((j, k))
                duration[j, k] = parts[j]["dur"][t]
        machine_classes = sorted(bytype)
        sets = [
            alternatives(bytype[t], sum(m[0] == t for m in machines))
            for t in machine_classes
        ]
        samples = {}
        total = valid = 0
        for candidate in itertools.product(*sets):
            total += 1
            assign = {}
            edges = defaultdict(list)
            degree = {n: 0 for n in duration}
            for m, queues in zip(machine_classes, candidate):
                for dup, ops in enumerate(queues, 1):
                    for node in ops:
                        assign[node] = (m, dup)
                    for a, b in zip(ops, ops[1:]):
                        edges[a].append(
                            (b, duration[a] + setup[parts[a[0]]["f"], parts[b[0]]["f"]])
                        )
                        degree[b] += 1
            for j in job_ids:
                for k in range(1, len(parts[j]["route"])):
                    a, b = (j, k - 1), (j, k)
                    edges[a].append(
                        (
                            b,
                            duration[a]
                            + transport[machines[assign[a]], machines[assign[b]]],
                        )
                    )
                    degree[b] += 1
            queue = [n for n in degree if degree[n] == 0]
            starts = {n: 0 for n in duration}
            done = 0
            while queue:
                n = queue.pop()
                done += 1
                for b, gap in edges[n]:
                    starts[b] = max(starts[b], starts[n] + gap)
                    degree[b] -= 1
                    if not degree[b]:
                        queue.append(b)
            if done != len(duration):
                continue
            valid += 1
            schedule = [
                dict(
                    j=j,
                    i=k,
                    m=list(assign[j, k]),
                    start=starts[j, k],
                    end=starts[j, k] + duration[j, k],
                )
                for j, k in duration
            ]
            end = {
                j: max(op["end"] for op in schedule if op["j"] == j) for j in job_ids
            }
            score = (
                max(end.values()),
                sum(max(0, end[j] - parts[j]["due"]) for j in job_ids),
            )
            samples.setdefault(score, schedule)
        return dict(tested=total, valid=valid, objectives=samples)

    aa = solve_component([2, 9])
    bb = solve_component([4, 22])
    candidate = {}
    for (x, y), t1 in aa["objectives"].items():
        for (xx, yy), t2 in bb["objectives"].items():
            score = max(x, xx), y + yy
            if score not in candidate:
                candidate[score] = t1 + t2
    pareto = [
        k
        for k in candidate
        if not any(v != k and v[0] <= k[0] and v[1] <= k[1] for v in candidate)
    ]
    for k in sorted(pareto):
        s = candidate[k]
        r = independently_check(machines, parts, s)
        assert r["ok"] and (r["makespan"], r["total_tardiness"]) == k
    return {
        "sequences": aa["tested"] * bb["tested"],
        "acyclic_sequences": aa["valid"] * bb["valid"],
        "nondominated": sorted(pareto),
    }
