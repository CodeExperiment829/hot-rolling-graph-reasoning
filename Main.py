"""Run the released production planning experiments."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.dont_write_bytecode = True
MODES = ("help","validate","demo","comparison","ablation","figures","tables","validate_figures","validate_tables")


def compute(mode, device):
    import publishing
    import planning
    import replanning
    from publishing import OUTPUT, write_json
    publishing.begin(mode)
    start = time.perf_counter()
    import benchmarks
    if mode == "demo":
        results = {name: module.run("demo") for name,module in
                   (("planning",planning),("replanning",replanning),("benchmarks",benchmarks))}
    else:
        results = {}
        if mode != "ablation":
            import calibration
            import full_line
            results["calibration"] = calibration.run()
            results["full_line"] = full_line.run()
            results["planning_comparison"] = planning.run("comparison")
            results["replanning_comparison"] = replanning.run("comparison")
            if mode != "figures":
                results["benchmark_comparison"] = benchmarks.run("comparison", device=device)
        if mode != "comparison":
            results["planning_ablation"] = planning.run("ablation")
            results["replanning_ablation"] = replanning.run("ablation")
            if mode != "figures":
                import conflicts
                results["conflicts"] = conflicts.run()
                if mode == "ablation":
                    results["benchmark_ablation"] = benchmarks.run("ablation", device=device)
    artifact_ids = []
    for path in sorted((OUTPUT / "validation/artifacts").glob("*.json")):
        if json.loads(path.read_text(encoding="utf-8"))["run_id"] == publishing.RUN_ID:
            artifact_ids.append(path.stem)
    resources = []
    bench = results.get("benchmark_comparison", {})
    if bench and bench["paired_Brandimarte"]["mean_ppo_seconds"] is None:
        resources.append("ReSched")
    split = bench.get("GTool_port_reordering") or results.get("benchmark_ablation",{}).get("GTool_port_reordering")
    if split and "status" in split and "unavailable" in split["status"].lower():
        resources.append("GTool split")
    receipt = {"mode":mode,"run_id":publishing.RUN_ID,"completed_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "elapsed_seconds":round(time.perf_counter()-start,3),"artifacts":artifact_ids,"limited_resources":resources}
    write_json(OUTPUT / mode / "summary.json",{**receipt, "results":results})
    write_json(OUTPUT / "validation/runs" / (publishing.RUN_ID+".json"),receipt)
    return receipt


def run_experiments(mode, device):
    import publishing
    output = publishing.OUTPUT
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output, prefix=".run-") as temporary:
        stage = Path(temporary)
        publishing.OUTPUT = stage
        try:
            receipt = compute(mode, device)
        finally:
            publishing.OUTPUT = output
        for item in sorted(stage.rglob("*")):
            if item.is_file():
                target = output / item.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(item,target)
    print(json.dumps(receipt,indent=2))
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=MODES,default="help")
    parser.add_argument("--device",choices=("auto","cpu","cuda"),default="auto",
                        help="ReSched inference device. Auto prefers an available GPU.")
    options=parser.parse_args()
    mode=options.mode
    if mode == "help":
        parser.print_help()
        return 0
    if mode.startswith("validate"):
        import validate
        if mode == "validate":
            print(json.dumps(validate.inputs(),indent=2))
            return 0
        report=validate.artifacts(mode.removeprefix("validate_"))
        print(json.dumps(report,indent=2))
        return int(report["status"] != "verified")
    return run_experiments(mode, options.device)


if __name__ == "__main__":
    sys.exit(main())

