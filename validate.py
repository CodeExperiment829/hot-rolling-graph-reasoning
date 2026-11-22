"""Check release inputs and verify delivered artifacts against their run receipts."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from PIL import Image
from publishing import OUTPUT, ROOT, markdown, write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inputs():
    from planning import load_cases, load_state_updates
    from replanning import load_events, load_expiry_calendars
    batches = read(ROOT / "Data/processing.json")
    conflicts = read(ROOT / "Data/conflicts.json")
    cases, events = load_cases(), load_events()
    observed = [len(batches), len(cases), len(events), len(conflicts)]
    if observed != [340,120,120,96]:
        raise ValueError(f"Unexpected case counts {observed}")
    for module in ("numpy","matplotlib","sklearn"):
        if importlib.util.find_spec(module) is None:
            raise ValueError("Missing dependency " + module)
    if shutil.which("node") is None:
        raise ValueError("Node.js is required for full-line planning")
    paired = load_state_updates(cases)
    calendars = load_expiry_calendars(events)
    line = read(ROOT / "Data/full_line.json")
    stand_ids = [s["id"] for s in line["stands"]]
    update = line["capacityUpdate"]
    if (len(stand_ids) != len(set(stand_ids)) or update["stand"] not in stand_ids
            or not update["baseline"] or not update["revised"]):
        raise ValueError("Incomplete full-line operating conditions.")
    from benchmark_resources import RESOURCES, resource
    available = {name: resource(name) is not None for name in RESOURCES}
    return {"processing_batches":observed[0],"initial_cases":observed[1],"execution_events":observed[2],
            "conflict_graphs":observed[3],"full_line_stands":len(stand_ids),
            "paired_state_updates":sum(len(r["updates"]) for r in paired),
            "expiry_calendars":len(calendars),"benchmark_resources":available}


def verify_one(key, spec, group):
    record = read(OUTPUT / "validation/artifacts" / (key+".json"))
    mode, run_id = record["mode"], record["run_id"]
    if mode not in ("comparison","ablation","figures","tables"):
        raise ValueError("No completed experiment receipt")
    receipt = read(OUTPUT / "validation/runs" / (run_id+".json"))
    if (mode,run_id) != (receipt["mode"],receipt["run_id"]) or key not in receipt["artifacts"]:
        raise ValueError("Experiment receipt mismatch")
    folder = OUTPUT / group
    pairs = ("csv","md") if group == "tables" else ("png","svg")
    for ext in pairs:
        current = (folder / f"{key}.{ext}").read_bytes()
        if hashlib.sha256(current).hexdigest() != record["rendered_file_sha256"][ext]:
            raise ValueError("Delivered file differs from the fresh render")
    if group == "tables":
        with (folder / (key+".csv")).open(encoding="utf-8",newline="") as stream:
            headers,*rows = csv.reader(stream)
        if len(rows) != spec["rows"] or len(headers) != spec["columns"] or any(len(r)!=len(headers) for r in rows):
            raise ValueError("Table dimensions differ from the registered layout")
        if (folder/(key+".md")).read_text(encoding="utf-8") != markdown(headers,rows,record["caption"],record["note"]):
            raise ValueError("CSV and Markdown cell values differ")
        complete = all(cell != "Unavailable" for r in rows for cell in r)
        if spec["experiment"] == "benchmarks" and receipt.get("limited_resources"):
            complete = False
        return {"structure":"verified","rows":len(rows),"columns":len(headers),"resource_coverage":"available" if complete else "partial",
                "run_id":run_id}
    with Image.open(folder/(key+".png")) as raster:
        raster.load()
        dpi = raster.info.get("dpi", (0,0))
        if min(dpi) < 299.9 or raster.width < 500 or raster.height < 250 or len(raster.getexif()):
            raise ValueError("Invalid raster resolution or metadata")
        for band in raster.convert("RGB").getextrema():
            if band[1] - band[0] < 5:
                raise ValueError("Empty figure")
    svg = ET.parse(folder/(key+".svg")).getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    if not list(svg.iter(namespace+"path")) or not list(svg.iter(namespace+"text")):
        raise ValueError("Expected vector shapes and labels")
    for tag in svg.iter():
        for name,value in tag.attrib.items():
            if name.endswith("href") and not(value.startswith("#") or value.startswith("data:image/")):
                raise ValueError("External SVG resource")
    return {"render":"verified","experiment":spec["experiment"],"panels":spec["panels"],"run_id":run_id}


def artifacts(group):
    specs = read(ROOT / "artifact_specs.json")[group]
    results = {}
    for key,spec in specs.items():
        try:
            results[key] = verify_one(key,spec,group)
        except (KeyError, ValueError, OSError, ET.ParseError) as exc:
            results[key] = {"error":type(exc).__name__, "check":"Review or regenerate this artifact."}
    status = "failed" if any("error" in r for r in results.values()) else "verified"
    summary = {"status":status,"check_scope":"Run association, file integrity and rendered structure. Paper agreement is assessed in the release report.",
               "artifacts":results}
    write_json(OUTPUT / "validation" / (group[:-1]+"_validation_summary.json"),summary)
    return summary

