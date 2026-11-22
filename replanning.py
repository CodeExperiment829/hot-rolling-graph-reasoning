"""Evaluate two-unit maintenance plans on the bundled event snapshots."""
import itertools
import json
import math
import statistics
import time
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np


EVENTS = ("无扰动", "能力变化", "进度延迟", "班组预约", "联合扰动")

METHODS = ("用途复用与冲突覆盖", "全图重算", "拓扑后继重算", "仅按有效期复用", "去除跨分支覆盖", "等权覆盖", "固定单点邻域")

USE_KEYS = ("A运行", "A完工", "B运行", "B完工")

WEIGHTS = dict(zip(USE_KEYS, (2, 6, 2, 6)))

THRESHOLD = 0.84

RATE = 5.0

def finish(mass, capacity, wait):
    return wait + math.ceil(mass / (RATE * capacity) - 1e-10)

def reference_finish(mass, capacity, wait):
    remaining = mass
    minutes = wait
    while remaining > 1e-8:
        remaining -= RATE * capacity
        minutes += 1
    return minutes

def overlap(a0,a1,b0,b1):
    return a0<b1 and b0<a1

def locked(t,d,e):
    return bool(e["lock"] and overlap(t,t+d,*e["lock"]))

def solve(e, releases, opened):
    """Enumerate legal starts for the open operations. Closed reservations keep their old start."""
    sets = []
    for key,release in zip(("a","b"),releases):
        old = e["old_"+key]
        starts = range(old, e["max_"+key] + 1) if key in opened else (old,)
        sets.append([s for s in starts if s >= release and not locked(s,e["d"+key],e)])
    best = None
    examined = 0
    for a,b in itertools.product(*sets):
        examined += 1
        if overlap(a,a+e["da"],b,b+e["db"]):
            continue
        score = ((a-e["old_a"])+(b-e["old_b"]), max(a+e["da"], b+e["db"]), a, b)
        if best is None or score<best:
            best=score
    return (list(best[-2:]) if best else None),examined

def conflicts(e,releases):
    req=[]
    for k,rel in zip(("a","b"),releases):
        t=e["old_"+k]
        if t<rel or locked(t,e["d"+k],e):req.append({k})
    # Project earliest individual changes. A newly displaced reservation may meet its independent peer.
    optimistic=[]
    for k,rel in zip(("a","b"),releases):
        c=[t for t in range(max(rel,e["old_"+k]), e["max_"+k]+1) if not locked(t,e["d"+k],e)]
        optimistic.append(c[0] if c else e["max_"+k]+1)
    a,b=optimistic
    if overlap(a,a+e["da"],b,b+e["db"]):req.append({"a","b"})
    return req

def get_neighborhood(req,scheme):
    if not req: return set()
    if scheme=="全图重算":return {"a","b"}
    if scheme=="固定单点邻域":
        return {min(("a","b"),key=lambda x:(-sum(x in edge for edge in req),x))}
    if scheme in ("拓扑后继重算","去除跨分支覆盖"):
        return {next(iter(ed)) for ed in req if len(ed)==1}
    ca,cb=(1,1) if scheme=="等权覆盖" else (2,1)
    options=[{x for i,x in enumerate(("a","b")) if mask&(1<<i)} for mask in range(4)]
    return min((s for s in options if all(s&ed for ed in req)),key=lambda s:(ca*("a" in s)+cb*("b" in s),len(s),sorted(s)))

def evaluate(e,method,tol=2):
    t0=time.perf_counter_ns()
    old=[e["q0"]>=THRESHOLD,finish(e["mass"],e["q0"],0),e["qb"]>=THRESHOLD,finish(e["mass_b"],e["qb"],0)]
    fresh=[e["q"]>=THRESHOLD,reference_finish(e["mass"],e["q"],e["wait"]),e["qb"]>=THRESHOLD,reference_finish(e["mass_b"],e["qb"],0)]
    updated=[False]*4
    changed=e["q"]!=e["q0"]
    if method=="全图重算":updated=[True]*4
    elif method=="拓扑后继重算":
        updated[:2]=[changed or not e["ttl"],changed or e["wait"]>0 or not e["ttl"]]
    elif method=="仅按有效期复用":
        updated[:2]=[not e["ttl"],not e["ttl"]]
    else:
        lo,hi=e["q"]-e["unc"], e["q"]+e["unc"]
        run_stable=(lo>=THRESHOLD and old[0]) or (hi<THRESHOLD and not old[0])
        earliest=finish(e["mass"],hi,e["wait"])
        latest=finish(e["mass"],lo,e["wait"])
        updated[:2]=[not(run_stable and e["ttl"]),not(e["ttl"] and max(abs(earliest-old[1]),abs(latest-old[1]))<=tol)]
    values=[f if u else o for f,u,o in zip(fresh,updated,old)]
    valid=[old[0]==fresh[0] and e["ttl"], abs(old[1]-fresh[1])<=tol and e["ttl"],True,True]
    wrong=[k for k,u,v in zip(USE_KEYS,updated,valid) if not u and not v]
    releases=values[1],values[3]
    req=conflicts(e,releases)
    opened=({"a","b"} if method=="全图重算" else get_neighborhood(req,method))
    initially=sorted(opened)
    sched,steps=solve(e,releases,opened)
    initial_sched=sched
    doubled=False
    if sched is None and len(opened)<2:
        opened={"a","b"};doubled=True
        sched,extra=solve(e,releases,opened);steps+=extra
    objective=None
    physically=bool(sched is not None and sched[0]>=fresh[1] and sched[1]>=fresh[3] and not locked(sched[0],e["da"],e) and not locked(sched[1],e["db"],e) and not overlap(sched[0],sched[0]+e["da"],sched[1],sched[1]+e["db"]))
    ok=physically and not wrong
    if sched is not None:
        objective=sum(t-old_t for t,old_t in zip(sched,(e["old_a"], e["old_b"])))
    # Aggregate abstract billing units, including re-dispatch of each released scheduling task.
    analysis_cost=sum(WEIGHTS[k] for k,u in zip(USE_KEYS,updated) if u)
    sched_cost=3*len(initially)+(6 if doubled else 0)
    wall=(time.perf_counter_ns()-t0)/1e6
    oracle,unused=solve(e,(fresh[1],fresh[3]),{"a","b"})
    return dict(id=e["id"],method=method,tol=tol,true_feasible=oracle is not None,ok=bool(ok),firstok=bool(ok and not doubled),
        reused=4-sum(updated),wrong=len(wrong),wrongkeys=wrong,true_reusable=sum(valid),missed=sum(u and v for u,v in zip(updated,valid)),use_valid=valid,
        analysis=analysis_cost,scheduler=sched_cost,cost=analysis_cost+sched_cost,wall_ms=wall,checks=steps,expanded=doubled,open=initially,conflict=[sorted(x) for x in req],
        changed_ops=(sum(t!=o for t,o in zip(sched,(e["old_a"],e["old_b"]))) if sched else None),shift_minutes=objective,
        plan=sched,oracle=oracle,updated=updated,old=old,fresh=fresh,executed=values,
        approx_delay=max(0,fresh[1]-(old[1]+3)),phys_ok=physically)

def mean(a):
    return round(statistics.mean(a),3) if a else None

def quantile(a,f):
    if not a: return None
    x=sorted(a);v=f*(len(x)-1);j=int(v)
    return round(x[j]+(x[min(j+1,len(x)-1)]-x[j])*(v-j),4)

def summarize(rows):
    feasible=[r for r in rows if r['true_feasible']]
    succ=[r for r in rows if r['ok']]
    reuse=sum(r['reused'] for r in rows)
    wrong=sum(r['wrong'] for r in rows)
    return dict(n=len(rows),proven=len(feasible),pass_n=len(succ),first_pass_n=sum(r['firstok'] for r in rows),
       reused=reuse,wrong=wrong,coverage=round(reuse/(4*len(rows))*100,2),wrong_rate=round(wrong/reuse*100,3) if reuse else None,
       true_reusable=sum(r['true_reusable'] for r in rows), missed=sum(r['missed'] for r in rows),
       cost=sum(r['cost'] for r in rows), cost_avg=mean([r['cost'] for r in rows]), cost_p95=quantile([r['cost'] for r in rows],.95),
       opened=mean([len(r['open']) for r in rows]), expanded=sum(r['expanded'] for r in rows),
       changed_ops_ok=mean([r['changed_ops'] for r in succ]), shift_min_ok=mean([r['shift_minutes'] for r in succ]),
       elapsed_p95_ms=quantile([r['wall_ms'] for r in rows],.95), candidate_pair_evals=sum(r["checks"] for r in rows))


DATA = Path(__file__).resolve().parent / "Data" / "replanning"
TOLERANCES = (0, 1, 2, 3, 5)
EXPIRY_INTERVALS = (1, 2, 4, 7, None)
METHOD_LABELS = (
    "Proposed local replanning method", "Full graph recomputation",
    "Recomputation of topological successors", "Reuse based solely on the validity period",
    "Without cross-branch coverage", "Equal-weight hitting set", "Fixed single-task neighborhood",
)
EVENT_LABELS = ("No disturbance", "Capacity change", "Progress delay",
                "Crew reservation change", "Combined disturbance")
INTENSITY_LABELS = ("Zero", "(0, 0.10]", "(0.10, 0.25]", ">0.25")
USE_LABELS = ("Valid reused", "Invalid reused", "Valid recomputed", "Invalid recomputed")


def load_events():
    events = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
    keys = {"id", "shift", "typ", "mass", "mass_b", "q0", "q", "qb", "wait", "ttl",
            "unc", "old_a", "old_b", "da_old", "da", "db", "max_a", "max_b", "lock"}
    if any(set(e) != keys or e["q"] <= e["unc"] or e["qb"] <= 0 for e in events):
        raise ValueError("Event fields or capacity interval invalid")
    shifts = {(e["shift"], e["typ"]) for e in events}
    expected = set(itertools.product(range(1, 25), EVENTS))
    if len(events) != len(expected) or shifts != expected or len({e["id"] for e in events}) != len(events):
        raise ValueError("Expected 24 distinct shifts, each with one event of each type")
    return events


def load_expiry_calendars(events):
    calendars = json.loads((DATA / "expiry_calendars.json").read_text(encoding="utf-8"))
    if tuple(c["interval_shifts"] for c in calendars) != EXPIRY_INTERVALS:
        raise ValueError("Incomplete set of expiry calendars.")
    known = {event["id"] for event in events}
    for calendar in calendars:
        ids = calendar["expired_events"]
        if len(set(ids)) != len(ids) or not set(ids) <= known:
            raise ValueError("Unexpected event in expiry calendar.")
    return calendars


def exact_calendar(e):
    """Independent minute-grid occupancy check for the two bounded start windows."""
    releases = [reference_finish(e["mass"], e["q"], e["wait"]),
                reference_finish(e["mass_b"], e["qb"], 0)]
    occupied = set(range(*e["lock"])) if e["lock"] else set()
    starts = []
    for unit, release in zip(("a", "b"), releases):
        free = []
        for start in range(max(e["old_" + unit], release), e["max_" + unit] + 1):
            slots = set(range(start, start + e["d" + unit]))
            if slots.isdisjoint(occupied):
                free.append((start, slots))
        starts.append(free)
    feasible = [(a, b) for (a, slots_a), (b, slots_b) in itertools.product(*starts)
                if slots_a.isdisjoint(slots_b)]
    if feasible:
        outcome = "feasible"
    elif all(starts):
        outcome = "shared-crew conflict"
    else:
        outcome = "empty individual window"
    return set(feasible), outcome


def audit_calendars(events, runs):
    reasons = Counter()
    for i, e in enumerate(events):
        feasible, reason = exact_calendar(e)
        reasons[reason] += 1
        for results in runs.values():
            r = results[i]
            physical = r["plan"] is not None and tuple(r["plan"]) in feasible
            if bool(feasible) != r["true_feasible"] or physical != r["phys_ok"]:
                raise ValueError("Calendar feasibility checks disagree")
            if r["ok"] != (physical and not r["wrong"]):
                raise ValueError("Whole-graph verification disagrees with the independent audit")
    return dict(reasons)


def cost_string(rows):
    mean_cost = Decimal(sum(r["cost"] for r in rows)) / Decimal(len(rows))
    return str(mean_cost.quantize(Decimal(".01"), rounding=ROUND_HALF_UP))


def use_counts(rows):
    counts = []
    for i in range(len(USE_KEYS)):
        counts.append([sum(r["updated"][i] == updated and r["use_valid"][i] == valid for r in rows)
                       for updated, valid in ((False, True), (False, False), (True, True), (True, False))])
    return counts


def disturbance_intensity(e, r):
    original_minutes = r["old"][1] + e["da_old"] + e["db"]
    locked_minutes = e["lock"][1] - e["lock"][0] if e["lock"] else 0
    added_minutes = r["fresh"][1] - r["old"][1] + e["da"] - e["da_old"] + locked_minutes
    return added_minutes / original_minutes


def cost_statistics(events, local, full):
    savings = np.array([b["cost"] - a["cost"] for a, b in zip(local, full)])
    shifts = np.array([e["shift"] for e in events])
    shift_means = np.array([savings[shifts == shift].mean() for shift in sorted(set(shifts))])
    draw = np.random.default_rng(20261118).integers(0, len(shift_means), (10000, len(shift_means)))
    interval = np.quantile(shift_means[draw].mean(axis=1), [.025, .975])
    disturbed = [i for i, e in enumerate(events) if e["typ"] != EVENTS[0]]
    local_cost = sum(local[i]["cost"] for i in disturbed)
    full_cost = sum(full[i]["cost"] for i in disturbed)
    return {"mean_saving": float(shift_means.mean()), "shift_bootstrap_95": interval.tolist(),
            "bootstrap_resamples": len(draw), "resampling_unit": "shift",
            "disturbed_cost_per_case": local_cost / len(disturbed),
            "disturbed_reduction_pct": 100 * (1 - local_cost / full_cost),
            "all_reduction_pct": 100 * savings.sum().item() / sum(r["cost"] for r in full)}


def initial_reservations(e):
    ports = json.loads((DATA / "baseline_ports.json").read_text(encoding="utf-8"))
    selected, release = [], []
    for machine, mass, q in (("RM-01", e["mass"], e["q0"]), ("RM-02", e["mass_b"], e["qb"])):
        for p in ports:
            end = finish(mass, p["q"], 0)
            if (p["machine"] == machine and p["quality"] >= .8 and p["lo"] <= q <= p["hi"]
                    and p["window"][0] <= 0 and end <= p["window"][1]):
                selected.append(p)
                release.append(end)
                break
        else:
            raise ValueError("No eligible baseline port")
    plan, count = solve(dict(e, lock=None, da=e["da_old"]), release, {"a", "b"})
    if plan != [e["old_a"], e["old_b"]]:
        raise ValueError("Baseline reservation does not match the pre-event snapshot")
    return selected, plan, count


def clock_time(minute):
    return f"{10 + minute // 60:02d}:{minute % 60:02d}"


def span(start, duration):
    return f"{clock_time(start)}–{clock_time(start + duration)}"


def write_trace(events, runs):
    from publishing import table
    i = next(i for i, e in enumerate(events) if e["id"] == "S01-E4")
    e, result = events[i], runs[METHODS[0]][i]
    ports, plan, checked = initial_reservations(e)
    j = next(i for i, e in enumerate(events) if e["id"] == "S24-E4")
    last = events[j]
    candidates, reason = exact_calendar(last)
    fixed_plan, _ = solve(e, (result["executed"][1], result["executed"][3]), set(result["open"]))
    if not (result["open"] == ["a"] and fixed_plan is None and result["expanded"] and result["ok"]
            and result["updated"][:2] == [False, True] and plan[0] < result["fresh"][1]
            and reason == "shared-crew conflict" and not candidates):
        raise ValueError("The example events do not support the reported trace stages")
    rows = [
        ["S01-pre, baseline", ", ".join(f"{p['id']} quality {p['quality']:.2f}" for p in ports),
         f"Bound the estimates to the two machines and checked {checked} candidate reservation pairs",
         f"RM-01 maintenance {span(plan[0], e['da_old'])}, RM-02 maintenance {span(plan[1], e['db'])}"],
        [e["id"] + ", feedback received",
         f"RM-01 load {e['q']:.3f}±{e['unc']:.3f}, additional wait of {e['wait']} min, crew occupied "
         + span(e["lock"][0], e["lock"][1] - e["lock"][0]),
         f"Retained the operating decision and updated the completion time from "
         f"{clock_time(result['old'][1])} to {clock_time(result['fresh'][1])}",
         "Original RM-01 reservation invalid"],
        [e["id"] + ", first attempt",
         "Hyperedges " + " and ".join("{" + ", ".join("RM-01" if u == "a" else "RM-02" for u in edge) + "}"
                                   for edge in result["conflict"]),
         f"Only the task with weight 2, RM-01, was opened. RM-02 remained scheduled to start at {clock_time(plan[1])}",
         f"RM-01 had no room in its window for {e['da']} min of maintenance"],
        [e["id"] + ", second attempt", "The conflict involved the shared crew, and RM-02 could still be rescheduled",
         f"Opened both reservations, scheduling RM-01 for {span(result['plan'][0], e['da'])} "
         f"and RM-02 for {span(result['plan'][1], e['db'])}",
         f"Both reservations passed final verification, with a total start time delay of {result['shift_minutes']} min"],
        [last["id"] + ", all tasks open",
         f"The latest maintenance start times were {clock_time(last['max_a'])} and {clock_time(last['max_b'])}, respectively",
         "Enumerated the two allowable windows minute by minute", "No feasible pair was found, and no new reservations were recorded"],
    ]
    table("table_16", ["Event and stage", "Basis for decision", "Task action", "Verification result"], rows,
          caption="Event log from the original reservations through final verification of the revised plan.")
    from replanning_figures import draw_trace
    draw_trace(e, result, runs[METHODS[1]][i])
    return e, result


def comparison(events):
    from publishing import table
    runs = {m: [evaluate(e, m) for e in events] for m in METHODS[:4]}
    local, full, topo, expiry = (runs[m] for m in METHODS[:4])
    reasons = audit_calendars(events, runs)
    totals = {METHOD_LABELS[i]: summarize(runs[m]) for i, m in enumerate(METHODS[:4])}
    table_rows = []
    for method_index in (1, 2, 3, 0):
        label = METHOD_LABELS[method_index]
        summary = totals[label]
        reuse = f"{summary['wrong']}/{summary['reused']}" if summary["reused"] else "Not applicable"
        table_rows.append([label, f"{summary['pass_n']}/{summary['n']}", reuse, cost_string(runs[METHODS[method_index]])])
    table("table_03", ["Strategy", "Plans passing whole-graph verification/events", "Incorrect reuses/total reuses",
                       "Recomputation cost per case/units"], table_rows,
          caption="Execution outcomes for different replanning strategies.")
    by_type = []
    for typ, label in zip(EVENTS, EVENT_LABELS):
        ix = [i for i, e in enumerate(events) if e["typ"] == typ]
        by_type.append([label, sum(local[i]["true_feasible"] for i in ix),
                        *(sum(row[i]["ok"] for i in ix) for row in (local, topo, expiry)),
                        cost_string([local[i] for i in ix])])
    table("table_12", ["Feedback type (24 cases each)", "Feasible by full enumeration",
                       "Verified with local replanning", "Verified after recomputing topological successors",
                       "Verified with validity-period reuse alone", "Mean local replanning cost (units)"],
          by_type, caption="Paired results for execution strategies on the same hot rolling events.")
    trace_event, trace = write_trace(events, runs)
    counts = use_counts(local)
    from replanning_figures import draw_intensity, draw_reuse
    draw_reuse(counts, trace_event, trace, THRESHOLD)
    bins = [[] for _ in INTENSITY_LABELS]
    for e, r in zip(events, local):
        intensity = disturbance_intensity(e, r)
        index = next(i for i, maximum in enumerate((0, .10, .25, math.inf)) if intensity <= maximum)
        bins[index].append(r)
    groups = [{"intensity": label, "n": len(rows), "expanded": sum(r["expanded"] for r in rows),
               "cost_mean": cost_string(rows), "p95_ms": quantile([r["wall_ms"] for r in rows], .95)}
              for label, rows in zip(INTENSITY_LABELS, bins)]
    savings = cost_statistics(events, local, full)
    draw_intensity(groups, savings, statistics.mean(r["cost"] for r in full))
    common = [i for i in range(len(events)) if all(row[i]["ok"] for row in (local, full, topo))]
    joint = {label: {"cases": len(common), "changed_reservations": sum(rr[i]["changed_ops"] for i in common),
                     "total_start_delay_min": sum(rr[i]["shift_minutes"] for i in common),
                     "mean_batch_delay_min": statistics.mean(rr[i]["approx_delay"] for i in common)}
             for label, rr in zip(METHOD_LABELS, (local, full, topo))}
    return {"strategies": totals, "independent_calendar_audit": reasons, "by_feedback": by_type,
            "reuse_categories": list(USE_LABELS), "use_counts_A_run_A_forecast_B_run_B_forecast": counts,
            "incorrect_ttl_reuse_by_use": [row[1] for row in use_counts(expiry)],
            "ttl_physically_feasible": sum(r["phys_ok"] for r in expiry),
            "intensity": groups, "cost_reduction": savings, "common_feasible_events": joint}


def ablation(events):
    from publishing import table
    indices = (0, 4, 5, 6, 1)
    runs = {METHODS[i]: [evaluate(e, METHODS[i]) for e in events] for i in indices}
    reasons = audit_calendars(events, runs)
    rows = []
    for i in indices:
        results = runs[METHODS[i]]
        edges = sum(len(r["conflict"]) for r in results)
        hits = sum(bool(set(r["open"]).intersection(edge)) for r in results for edge in r["conflict"])
        label = {0: "Proposed weighted hitting set", 1: "Full graph reopening and recomputation"}.get(i, METHOD_LABELS[i])
        rows.append([label, f"{hits}/{edges}", sum(r["firstok"] for r in results),
                     sum(r["expanded"] for r in results), sum(r["ok"] for r in results), cost_string(results)])
    table("table_14", ["Neighborhood strategy", f"Hyperedges covered on first attempt/{sum(len(r['conflict']) for r in runs[METHODS[0]])}",
                       "Events passing first attempt/120", "Neighborhood expansions",
                       "Events passing final verification/120", "Mean cost/units"], rows,
          caption="Effect of replanning neighborhood selection on conflict resolution.")
    sensitivity = []
    for tol in TOLERANCES:
        results = [evaluate(e, METHODS[0], tol) for e in events]
        sensitivity.append({"tolerance": tol, "reuse_count": sum(r["reused"] for r in results),
                            "incorrect_reuses": sum(r["wrong"] for r in results),
                            "verified": sum(r["ok"] for r in results), "cost_mean": cost_string(results),
                            "feasible_failures": sum(r["true_feasible"] and not r["ok"] for r in results)})
    from replanning_figures import draw_tolerance
    draw_tolerance(sensitivity)
    expiry = []
    for calendar in load_expiry_calendars(events):
        expired = set(calendar["expired_events"])
        results = [evaluate(dict(e, ttl=e["id"] not in expired), METHODS[0]) for e in events]
        expiry.append({"interval_shifts": calendar["interval_shifts"], "reuse_count": sum(r["reused"] for r in results),
                       "verified": sum(r["ok"] for r in results), "cost_mean": cost_string(results)})
    return {"neighborhoods": rows, "tolerance_sensitivity": sensitivity, "expiry_sensitivity": expiry,
            "capacity_two_example": cumulative_check(),
            "independent_calendar_audit": reasons}


def cumulative_check():
    """Test the three reservations that share a capacity-two resource."""
    case = json.loads((DATA / "shared_resource.json").read_text(encoding="utf-8"))
    capacity, ops = case["capacity"], case["operations"]

    def occupancy(operations):
        slots = Counter()
        for op in operations:
            slots.update(range(op["start"], op["end"]))
        return slots

    load = occupancy(ops)
    peaks = [max(occupancy(pair).values()) for pair in itertools.combinations(ops, 2)]
    overloaded = sorted(t for t, n in load.items() if n > capacity)
    conflicts_at = [{i for i, op in enumerate(ops) if op["start"] <= t < op["end"]} for t in overloaded]
    candidates = (set(ix) for size in range(len(ops) + 1) for ix in itertools.combinations(range(len(ops)), size))
    selected = min((ix for ix in candidates if all(ix & group for group in conflicts_at)),
                   key=lambda ix: (sum(ops[i]["weight"] for i in ix), len(ix), sorted(ix)))
    adjusted = [dict(op) for op in ops]
    for i in selected:
        other = [op for j, op in enumerate(adjusted) if j != i]
        existing_load = occupancy(other)
        duration = ops[i]["end"] - ops[i]["start"]
        start = ops[i]["start"]
        while any(existing_load[t] >= capacity for t in range(start, start + duration)):
            start += 1
        adjusted[i].update(start=start, end=start + duration)
    return {"initial_peak": max(load.values()), "all_pairs_feasible": max(peaks) <= capacity,
            "overloaded_minutes": overloaded, "opened_weight": sum(ops[i]["weight"] for i in selected),
            "adjusted_intervals": [[adjusted[i]["start"], adjusted[i]["end"]] for i in sorted(selected)],
            "adjusted_peak": max(occupancy(adjusted).values())}


def run(mode):
    events = load_events()
    if mode == "comparison":
        return comparison(events)
    if mode == "ablation":
        return ablation(events)
    if mode == "demo":
        event = next(e for e in events if e["id"] == "S01-E4")
        local, full = (evaluate(event, m) for m in METHODS[:2])
        calendars = audit_calendars([event], {METHODS[0]: [local], METHODS[1]: [full]})
        return {"local": summarize([local]), "full": summarize([full]),
                "independent_calendar_audit": calendars}
    raise ValueError("Unknown replanning mode")
