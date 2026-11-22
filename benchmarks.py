"""Independent evaluation of the public benchmarks in Appendix C."""
import json
from statistics import mean
from time import perf_counter

from benchmark_lib import cell, gtool, resched
from benchmark_lib.reference_rules import (
    ROOT,
    dispatch,
    galvanizing,
    list_schedule,
    read_fjsp,
    taskbench,
)
from benchmark_resources import resource
from publishing import table


def compare_native_record(jobs, path):
    """Check the official one-based encoding against the zero-based benchmark."""
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    if int(lines[0].split()[0]) != len(jobs) or len(lines) != len(jobs) + 1:
        raise ValueError("Incompatible job counts across archives")
    for job, line in zip(jobs, lines[1:]):
        numbers = iter(map(int, line.split()))
        if next(numbers) != len(job):
            raise ValueError("Incompatible operation counts across archives")
        for options in job:
            other = [(next(numbers) - 1, next(numbers)) for _ in range(next(numbers))]
            if sorted(other) != sorted(options):
                raise ValueError(
                    "Different eligible machines or durations across archives"
                )
        if list(numbers):
            raise ValueError("Unexpected trailing operation data")


def average_gap(rows, method):
    return mean(100 * (r[method] / r["reference"] - 1) for r in rows)


def schedule_suite(device="auto"):
    records = json.loads((ROOT / "instances.json").read_text(encoding="utf8"))
    model, status = resched.policy(device)
    rows = []
    for record in records:
        family, _ = record["path"].split("/")
        raw = (ROOT / record["path"]).read_bytes()
        jobs = read_fjsp(raw)
        machine_count = int(raw.splitlines()[0].split()[1])
        item = {
            "family": family,
            "name": record["name"],
            "operations": sum(map(len, jobs)),
            "reference": record["optimum"] or record["bounds"]["upper"],
            "FCFS": list_schedule(jobs, "FCFS"),
            "ECT": list_schedule(jobs, "ECT"),
        }
        paired = family == "brandimarte" and int(record["name"][2:]) <= 10
        if paired:
            idx = int(record["name"][2:])
            compare_native_record(jobs, ROOT / "ReSched" / f"BrandimarteMk{idx}.fjs")
            tick = perf_counter()
            item["calendar"] = min(dispatch(jobs, rule) for rule in range(3))
            item["calendar_seconds"] = perf_counter() - tick
        if model is not None and (paired or family == "fattahi"):
            item["PPO"], item["PPO_seconds"] = resched.infer(model, jobs, machine_count)
        rows.append(item)
    summary = {}
    for family in sorted({r["family"] for r in rows}):
        members = [r for r in rows if r["family"] == family]
        metrics = {
            "instances": len(members),
            "operations": sum(r["operations"] for r in members),
        }
        for method in ("FCFS", "ECT", "PPO"):
            subset = [r for r in members if method in r]
            if subset:
                metrics[method] = {
                    "count": len(subset),
                    "mean_makespan": mean(r[method] for r in subset),
                    "mean_relative_gap_pct": average_gap(subset, method),
                }
        summary[family] = metrics
    paired = sorted(
        (r for r in rows if "calendar" in r), key=lambda r: int(r["name"][2:])
    )
    return paired, summary, status


def publish_scheduling(paired, status):
    has_policy = all("PPO" in row for row in paired)
    missing = "Unavailable"
    labels = [
        ("PPO", "ReSched"),
        ("calendar", "Proposed resource calendar scheduling method"),
    ]
    means, gaps = {}, {}
    for method, _ in labels:
        if method == "PPO" and not has_policy:
            means[method] = gaps[method] = missing
        else:
            means[method] = f"{mean(row[method] for row in paired):.1f}"
            gaps[method] = f"{average_gap(paired, method):.2f}%"
    table(
        "table_02b",
        [
            "Brandimarte instances (Mk01–Mk10)",
            "Mean makespan",
            "Mean relative gap from reference",
        ],
        [[label, means[method], gaps[method]] for method, label in labels],
        "Table 2B. Feasibility of initial production plans within the search budget.",
        status,
    )
    body = [
        [r["name"].capitalize(), r["reference"], r.get("PPO", missing), r["calendar"]]
        for r in paired
    ]
    body += [
        [
            "Mean makespan",
            f'{mean(r["reference"] for r in paired):.1f}',
            means["PPO"],
            means["calendar"],
        ],
        ["Mean relative gap across instances", "0", gaps["PPO"], gaps["calendar"]],
    ]
    table(
        "table_11",
        [
            "Brandimarte instance",
            "Known feasible reference value",
            "ReSched",
            "Resource calendar scheduling",
        ],
        body,
        "Table 11. Results of the initial scheduling module on public instances.",
        status,
    )
    return {
        "instances": len(paired),
        "operations": sum(r["operations"] for r in paired),
        "mean_makespan": means,
        "mean_relative_gap": gaps,
        "mean_calendar_seconds": mean(r["calendar_seconds"] for r in paired),
        "mean_ppo_seconds": mean(r["PPO_seconds"] for r in paired)
        if has_policy
        else None,
        "shorter_calendars": sum(r["calendar"] < r["PPO"] for r in paired)
        if has_policy
        else None,
        "ties": sum(r["calendar"] == r["PPO"] for r in paired) if has_policy else None,
        "shorter_ppo": sum(r["PPO"] < r["calendar"] for r in paired)
        if has_policy
        else None,
    }


def run(mode, device="auto"):
    if mode == "demo":
        jobs = read_fjsp((ROOT / "brandimarte/mk01.txt").read_bytes())
        return {
            "instance": "Mk01",
            "calendar_makespan": min(dispatch(jobs, p) for p in range(3)),
        }
    if mode == "ablation":
        corpus = resource("gtool_multimedia.jsonl")
        return {
            "GTool_port_reordering": gtool.evaluate_split(corpus)
            if corpus
            else {"status": "Input unavailable. Run python -m benchmark_resources."}
        }
    paired, families, status = schedule_suite(device)
    summary = publish_scheduling(paired, status)
    split = run("ablation")["GTool_port_reordering"]
    optional_note = split.get("status") or f'{split["changed"]} test requests reordered'
    table(
        "table_10",
        ["Comparison method", "Evaluation basis", "Evaluation in this run"],
        [
            ["GTool", "Published reference on ToolBench", optional_note],
            ["ToolTree", "Published reference on GTA", "Literature comparison"],
            [
                "ReSched",
                "Released PPO policy on Mk01–Mk10",
                f'{status}. Mean makespan {summary["mean_makespan"]["PPO"]}. '
                f'Mean relative gap {summary["mean_relative_gap"]["PPO"]}.',
            ],
            [
                "RACE-Sched",
                "Published references on GEN-Bench and JMS-Bench",
                "Literature comparison",
            ],
            [
                "MOPN-KT",
                "Published hot-rolling order planning study",
                "Literature comparison",
            ],
            ["SLR2", "Published study on held-out Mk6–Mk10", "Literature comparison"],
        ],
        "Table 10. Published benchmark results and third-party implementations used in the comparisons.",
        "Literature-only scores are cited in the manuscript. ReSched and the retrieval rules have runnable evaluations.",
    )
    return {
        "ReSched_status": status,
        "paired_Brandimarte": summary,
        "dispatching_families": families,
        "TaskBench": taskbench(),
        "GTool_port_reordering": split,
        "manufacturing_cell": cell.evaluate_dispatch(),
        "cell_Ins1": cell.exact_first_instance(),
        "galvanizing": galvanizing(),
    }
