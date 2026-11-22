"""Initial planning and paired state-update experiments."""

from collections import Counter
import itertools
import json
import math
from pathlib import Path
import statistics
import time

from publishing import figure, table


DATA = Path(__file__).resolve().parent / "Data" / "planning"
BUDGET = 60
BUDGETS = (30, 60, 120, 165)
STRATEGIES = {
    "terminal": (False, False),
    "no_input": (False, True),
    "no_resource": (True, False),
    "full": (True, True),
}
LABELS = {
    "terminal": "Checking only complete plans",
    "no_input": "Without input screening",
    "no_resource": "Without incremental resource pruning",
    "full": "Proposed method",
}
GROUPS = {
    "ordinary": "Baseline",
    "input_perturbation": "Input disturbance",
    "resource_perturbation": "Resource disturbance",
    "blocked": "Equipment lockout",
    "quality_pending": "Unverified quality",
}


def independent_check(case, s, start, maintenance, assume_quality=False):
    # Independent minute-wise replay. This verifier does not call search or overlap tests.
    dur=math.ceil(60*case["tons"]/s["rate"])
    end=start+dur
    required=(s["object"]==case["object"] and s["lo"]<=case["load"]<=s["hi"] and end<=s["valid_until"])
    quality=s["quality"]
    if not required or (quality is None and not assume_quality) or (quality is not None and quality<.8): return False
    if end>maintenance: return False
    finish=maintenance+case["maintenance_duration"]
    for t in range(max(finish,end)):
        is_maintenance=maintenance<=t<finish
        machine_demand=int(start<=t<end)+int(is_maintenance)+sum(a<=t<b for a,b in case["machine_locked"])
        crew_demand=int(is_maintenance)+sum(a<=t<b for a,b in case["crew_locked"])
        if machine_demand>1 or crew_demand>1: return False
    return True


def enumerate_truth(case):
    paths=list(itertools.product(case["sources"],case["roll_starts"],case["maintain_starts"]))
    ok=[(s["id"],r,m) for s,r,m in paths if independent_check(case,s,r,m)]
    maybe=[] if ok else [(s["id"],r,m) for s,r,m in paths if independent_check(case,s,r,m,True)]
    return ("feasible" if ok else "pending" if maybe else "infeasible"),ok,maybe


def search(case, inputs, resources, budget):
    expanded=0; leaves=0; rejected=0; pruned_input=0; pruned_resource=0; hit_pending=False
    def debit():
        nonlocal expanded
        if expanded>=budget: raise TimeoutError
        expanded+=1
    def overlap(a,b,locks):return any(a<y and x<b for x,y in locks)
    def info(status,plan=None):
        return dict(status=status,plan=plan,expanded=expanded,leaves=leaves,rejected_terminal=rejected,pruned_input=pruned_input,pruned_resource=pruned_resource)
    try:
        for s in case["sources"]:
            debit()
            compat=s["object"]==case["object"] and s["lo"]<=case["load"]<=s["hi"]
            if inputs and (not compat or (s["quality"] is not None and s["quality"]<.8)):
                pruned_input+=1;continue
            if inputs and s["quality"] is None:
                hit_pending=True;pruned_input+=1;continue
            for r in case["roll_starts"]:
                debit()
                end=r+math.ceil(60*case["tons"]/s["rate"])
                if inputs and end>s["valid_until"]:
                    pruned_input+=1;continue
                if resources and overlap(r,end,case["machine_locked"]):
                    pruned_resource+=1;continue
                for m in case["maintain_starts"]:
                    debit()
                    finish=m+case["maintenance_duration"]
                    if resources and (m<end or overlap(m,finish,case["machine_locked"]) or overlap(m,finish,case["crew_locked"])):
                        pruned_resource+=1;continue
                    leaves+=1
                    if independent_check(case,s,r,m):return info("ok",[s["id"],r,m])
                    elif s["quality"] is None and independent_check(case,s,r,m,True):hit_pending=True
                    rejected+=1
    except TimeoutError:
        return info("budget")
    return info("pending" if hit_pending else "exhausted")

def load_cases():
    cases = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Each planning case needs a unique identifier.")
    if {case["setting"] for case in cases} != set(GROUPS):
        raise ValueError("The planning case groups are incomplete.")
    return cases


def load_state_updates(cases):
    records = json.loads((DATA / "state_updates.json").read_text(encoding="utf-8"))
    kinds = {"ordinary": {"load", "expiry", "crew"}, "quality_pending": {"quality"}}
    expected = {c["id"]: c["setting"] for c in cases if c["setting"] in kinds}
    seen = set()
    for record in records:
        before, updates = record["baseline"], record["updates"]
        key = before["id"]
        if key in seen or key not in expected or before["setting"] != expected[key]:
            raise ValueError("Unexpected or duplicate baseline in the state-update input.")
        if set(updates) != kinds[expected[key]] or any(c["id"] != key for c in updates.values()):
            raise ValueError("Incomplete or mismatched state-update pair.")
        seen.add(key)
    if seen != set(expected):
        raise ValueError("Missing baseline in the state-update input.")
    return records


def sync_experiment(cases):
    """Evaluate current and stale plans against each supplied post-update state."""
    counts = {k: Counter() for k in ("load", "expiry", "crew", "quality")}
    for record in load_state_updates(cases):
        before = record["baseline"]
        initial = search(before, True, True, BUDGET)
        plan = initial["plan"]
        if before["setting"] == "ordinary" and (not verified(before, plan) or plan[0] != "primary"):
            raise ValueError("The paired initial plan is invalid.")
        for event, changed in record["updates"].items():
            new_plan = search(changed, True, True, BUDGET)["plan"]
            pair = counts[event]
            pair["cases"] += 1
            if event == "quality":
                pair["recovered_after_confirmation"] += int(initial["status"] == "pending" and verified(changed, new_plan))
                continue
            pair["stale_pass"] += int(verified(changed, plan))
            pair["updated_pass"] += int(verified(changed, new_plan))
            pair["feasible_by_enumeration"] += int(enumerate_truth(changed)[0] == "feasible")
    return {event: dict(group) for event, group in counts.items()}


def verified(case, plan):
    if plan is None:
        return False
    source = next(s for s in case["sources"] if s["id"] == plan[0])
    return independent_check(case, source, plan[1], plan[2])


def solve(cases):
    outcomes = []
    for case in cases:
        truth, feasible, _ = enumerate_truth(case)
        by_method = {}
        for method, (screen, prune) in STRATEGIES.items():
            limited = search(case, screen, prune, BUDGET)
            complete = search(case, screen, prune, max(BUDGETS))
            if complete["status"] == "budget" and truth == "feasible":
                # A new case may need more than the displayed budget range.
                complete = search(case, screen, prune, math.inf)
            if (complete["plan"] is not None) != bool(feasible):
                raise ValueError("Search disagrees with exhaustive enumeration.")
            for result in (limited, complete):
                if result["plan"] and tuple(result["plan"]) not in feasible:
                    raise ValueError("A search returned an invalid plan.")
            by_method[method] = {
                "limited": limited,
                "first_solution_node": complete["expanded"] if complete["plan"] else None,
            }
        outcomes.append((case, truth, by_method))
    return outcomes


def aggregate(outcomes):
    summary = {}
    for method in STRATEGIES:
        results = [by_method[method]["limited"] for _, _, by_method in outcomes]
        first = [
            by_method[method]["first_solution_node"]
            for _, truth, by_method in outcomes if truth == "feasible"
        ]
        if any(n is None for n in first):
            raise ValueError("A feasible case has no first solution.")
        summary[method] = {
            "status_counts": dict(Counter(r["status"] for r in results)),
            "mean_expanded": statistics.mean(r["expanded"] for r in results),
            "invalid_complete": sum(r["rejected_terminal"] for r in results),
            "coverage": [sum(n <= b for n in first) for b in range(max(BUDGETS) + 1)],
            "budget_for_all_feasible": max(first, default=None),
            "group_mean_expanded": {
                group: statistics.mean(by_method[method]["limited"]["expanded"]
                                       for case, _, by_method in outcomes if case["setting"] == group)
                for group in GROUPS
            },
        }
    return summary


def joint_delays(outcomes):
    modes = ("full", "terminal")
    delays = {mode: [] for mode in modes}
    for case, _, by_method in outcomes:
        plans = [by_method[m]["limited"]["plan"] for m in modes]
        if all(plans):
            for method, (source_id, start, _) in zip(modes, plans):
                source = next(s for s in case["sources"] if s["id"] == source_id)
                end = start + math.ceil(60 * case["tons"] / source["rate"])
                delays[method].append(max(0, end - case["due_min"]))
    return {"cases": len(delays["full"]), "mean_delay_minutes": {
        m: statistics.mean(v) if v else None for m, v in delays.items()
    }}


def timing(cases):
    """Median of ten full sequential sweeps after an additional warm-up sweep."""
    measurements = {}
    for method, (screen, prune) in STRATEGIES.items():
        samples = []
        for _ in range(11):
            start = time.perf_counter_ns()
            for case in cases:
                search(case, screen, prune, BUDGET)
            samples.append((time.perf_counter_ns() - start) / 1e6 / len(cases))
        measurements[method] = statistics.median(samples[1:])
    return measurements


def render_figure(stats, feasible_count, group_counts):
    import matplotlib.pyplot as plt

    ink = "#111111"
    blue, purple, grey = "#236db0", "#81758e", "#59636a"
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.29))
    fig.subplots_adjust(left=.047, right=.982, top=.78, bottom=.27, wspace=.22)
    left, right = axes
    left.set_position([.045, .267, .418, .517])
    right.set_position([.553, .284, .429, .5])
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["bottom", "left"]].set_color("#859ba5")
        ax.tick_params(colors=ink, labelsize=14)
        ax.grid(axis="y", color="#d7e1e4", linewidth=.6)
        ax.set_axisbelow(True)
    titles = ("(a)  Search budget for the first feasible plan",
              "(b)  Effect of resource pruning on search effort")
    group_sizes = set(group_counts.values())
    subtitle = (f"Mean nodes expanded ({next(iter(group_sizes))} cases per group)"
                if len(group_sizes) == 1 else "Mean nodes expanded per case group")
    for ax, title, label in zip(axes, titles,
                                (f"Cumulative cases solved ({feasible_count} known feasible cases)", subtitle)):
        ax.text(-.075, 1.27, title, transform=ax.transAxes, fontsize=19, fontweight="bold", color=ink)
        ax.text(-.075, 1.13, label, transform=ax.transAxes, fontsize=15, color=ink)
    budgets = range(max(BUDGETS) + 1)
    for method, label, color, style, width in [
        ("full", "Proposed method", blue, "-", 2.0),
        ("no_input", "No input screening", purple, (0, (8, 3)), 1.2),
        ("terminal", "Check complete plans only", grey, (0, (4, 2, 1, 2)), 1.2),
    ]:
        left.step(budgets, stats[method]["coverage"], where="post", label=label,
                  color=color, linestyle=style, linewidth=width, zorder=4 if method == "full" else 2)
    left.axvline(BUDGET, color="#a6b4b8", linewidth=.85, linestyle=(0,(3,3)))
    left.set_xlim(0, max(BUDGETS))
    left.set_xticks(range(0, max(BUDGETS) + 1, 30))
    left.set_ylim(0, feasible_count * 1.04)
    left.set_yticks(range(0, feasible_count + 1, max(1, feasible_count // 6)))
    left.set_xlabel("Candidate node budget", labelpad=8, color=ink, fontsize=16)
    positions = range(len(GROUPS))
    for method, label, offset, color in [
        ("no_resource", "No incremental resource pruning", -.19, "#bbc3c8"),
        ("full", "Proposed method", .19, blue)
    ]:
        values = [stats[method]["group_mean_expanded"][k] for k in GROUPS]
        bars = right.bar([x + offset for x in positions], values, width=.38, color=color, label=label)
        for bar, key, val in zip(bars, GROUPS, values):
            if key in ("resource_perturbation", "blocked"):
                right.annotate(f"{val:.1f}", (bar.get_x() + bar.get_width()/2, val),
                               xytext=(0, 3), textcoords="offset points", ha="center", fontsize=11.5, color=ink)
    right.set_xticks(list(positions), [s.replace(" ", "\n") for s in GROUPS.values()])
    right.tick_params(axis="x", length=0, labelsize=11)
    right.set_ylim(0, max(50, right.get_ylim()[1]))
    right.set_xlabel("Case group", color=ink, fontsize=16)
    for ax, ncol in ((left, 3), (right, 2)):
        ax.legend(loc="upper center", bbox_to_anchor=(.5, -.35), ncols=ncol, fontsize=13,
                  handlelength=1.7, handletextpad=.45, columnspacing=.8, frameon=False)
    from matplotlib.text import Text

    for label in fig.findobj(Text):
        label.set_fontfamily(["Times New Roman", "DejaVu Serif"])
    try:
        figure("figure_06", fig)
    finally:
        plt.close(fig)


def run(mode):
    cases = load_cases()
    if mode == "demo":
        case = next(c for c in cases if c["setting"] == "resource_perturbation")
        truth, feasible, _ = enumerate_truth(case)
        result = search(case, True, True, BUDGET)
        if not verified(case, result["plan"]):
            raise ValueError("The demo verifier rejected the plan.")
        return {"feasible_combinations": len(feasible),
                "status": result["status"], "expanded": result["expanded"]}
    if mode not in ("comparison", "ablation"):
        raise ValueError(f"Unknown planning experiment {mode}")
    outcomes = solve(cases)
    stats = aggregate(outcomes)
    counts = dict(Counter(truth for _, truth, _ in outcomes))
    n_feasible = counts["feasible"]
    result = {"n_cases": len(cases), "budget": BUDGET, "truth": counts, "strategies": stats,
              "joint_feasible_delay": joint_delays(outcomes)}
    groups = dict(Counter(c["setting"] for c in cases))
    render_figure(stats, n_feasible, groups)
    if mode == "comparison":
        rows = []
        for method, label in (
            ("terminal", "Same candidates, checking only complete plans"),
            ("no_resource", LABELS["no_resource"]), ("full", "Proposed task graph generation method"),
        ):
            rows.append([label, f"{stats[method]['coverage'][BUDGET]}/{n_feasible}",
                         f"{stats[method]['mean_expanded']:.2f}"])
        table("table_02a", ["A Fixed candidate tasks for hot rolling", "Cases solved/known feasible cases",
                            f"Mean number of nodes expanded ({len(cases)} cases)"], rows,
              caption="Feasibility of initial production plans within the search budget.")
        result["synchronization"] = sync_experiment(cases)
    else:
        times = timing(cases)
        result["median_search_ms_per_case"] = times
        rows = [[LABELS[method], *[stats[method]["coverage"][budget] for budget in BUDGETS],
                 f"{stats[method]['invalid_complete']:,}"] for method in STRATEGIES]
        timing_text = ", ".join(f"{times[m]:.4f}" for m in STRATEGIES)
        table("table_13", ["Strategy", *[f"Cases solved with a budget of {b}" for b in BUDGETS],
                           f"Invalid complete combinations at a budget of {BUDGET}"], rows,
              caption="Task graph generation ablation results with the same candidate set.",
              note=(f"Solved counts use {n_feasible} known feasible cases. Invalid combinations cover "
                    f"all {len(cases)} cases. Median search time per case in table order (ms): {timing_text}."))
    return result
