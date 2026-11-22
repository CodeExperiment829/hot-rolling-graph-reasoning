"""Publish fresh experiment artifacts with a common run identifier."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from uuid import uuid4

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
STYLE = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["graphics"]
plt.rcParams.update({"font.family": "serif", "font.serif": STYLE["fonts"]})
OUTPUT = ROOT / "outputs"
RUN_ID = uuid4().hex
MODE = "standalone"


def begin(mode):
    global MODE, RUN_ID
    MODE, RUN_ID = mode, uuid4().hex


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def markdown(headers, rows, caption, note):
    def line(row):
        return "| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", "<br>") for cell in row) + " |"
    lines = ([caption, ""] if caption else []) + [line(headers), line(["---"] * len(headers))]
    lines.extend(line(row) for row in rows)
    if note:
        lines.extend(["", note])
    return "\n".join(lines) + "\n"


def publish(key, directory, files, details):
    if not key.replace("_", "").isalnum():
        raise ValueError("Invalid artifact name")
    fingerprints = {}
    for ext, data in files.items():
        write_bytes(OUTPUT / directory / (key + "." + ext), data)
        fingerprints[ext] = hashlib.sha256(data).hexdigest()
    write_json(OUTPUT / "validation" / "artifacts" / (key + ".json"), {
        "artifact": key, "mode": MODE, "run_id": RUN_ID,
        "rendered_file_sha256": fingerprints, **details,
    })


def table(key, headers, rows, caption="", note=""):
    if MODE in ("figures", "demo"):
        return
    headers = list(map(str, headers))
    rows = [list(map(str, row)) for row in rows]
    if not rows or any(len(row) != len(headers) for row in rows):
        raise ValueError(f"Invalid row width in {key}")
    stream = io.StringIO(newline="")
    csv.writer(stream).writerows([headers] + rows)
    publish(key, "tables", {
        "csv": stream.getvalue().encode("utf-8"),
        "md": markdown(headers, rows, caption, note).encode("utf-8"),
    }, {"rows": len(rows), "columns": len(headers), "caption": caption, "note": note})


def figure(key, fig):
    try:
        if MODE in ("tables", "demo"):
            return
        rendered = {}
        for ext in ("png", "svg"):
            buffer = io.BytesIO()
            metadata = {"Software": None} if ext == "png" else {"Creator": None, "Date": None}
            with matplotlib.rc_context({"svg.fonttype": "none"}):
                fig.savefig(buffer, format=ext, dpi=STYLE["dpi"], metadata=metadata, bbox_inches="tight",
                            pad_inches=0.10, facecolor="white")
            rendered[ext] = buffer.getvalue()
        publish(key, "figures", rendered, {"axes": len(fig.axes), "dpi": STYLE["dpi"]})
    finally:
        plt.close(fig)

