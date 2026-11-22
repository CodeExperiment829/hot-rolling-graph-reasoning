"""Shift-disjoint least-squares duration forecasts and finite-sample intervals."""
import json
import math

import matplotlib.pyplot as plt
import numpy as np

from publishing import ROOT, figure, table


def metrics(errors, radius):
    return {"n": len(errors), "mae": float(abs(errors).mean()), "p90": float(np.quantile(abs(errors), .9)),
            "bias": float(errors.mean()), "covered": int((abs(errors) <= radius).sum())}


def run():
    settings = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["calibration"]
    records = json.loads((ROOT / "Data/processing.json").read_text(encoding="utf-8"))
    subsets = np.array([r["subset"] for r in records])
    shifts = np.array([r["shift"] for r in records])
    for shift in np.unique(shifts):
        if len(set(subsets[shifts == shift])) != 1:
            raise ValueError("A shift crosses the split boundary")
    x = np.array([60*r["tons"] / (settings["capacity_tph"]*r["observed_load"]) for r in records])
    features = np.column_stack([np.ones_like(x), x, x * [r["hard_grade"] for r in records]])
    actual = np.array([r["duration_min"] for r in records])
    fit, cal, test = [subsets == name for name in ("fit", "cal", "test")]
    beta = np.linalg.lstsq(features[fit], actual[fit], rcond=None)[0]
    predictions = features @ beta
    errors = predictions - actual
    ranked = np.sort(abs(errors[cal]))
    levels = settings["levels"]
    radii = [float(ranked[min(len(ranked), math.ceil((len(ranked)+1)*level))-1]) for level in levels]
    coverage = [int((abs(errors[test]) <= radius).sum()) for radius in radii]
    states = np.array([r["state"] for r in records])
    radius = radii[levels.index(.9)]
    groups = {k: metrics(errors[test & (states == k)], radius) for k in ("normal", "derated", "low_quality")}
    all_test = metrics(errors[test], radius)
    shift_mae = np.array([abs(errors[test & (shifts == i)]).mean() for i in np.unique(shifts[test])])
    rng = np.random.default_rng(settings["bootstrap_seed"])
    draws = rng.choice(shift_mae, (settings["bootstrap_samples"], len(shift_mae)), replace=True)
    ci = np.quantile(draws.mean(axis=1), [.025, .975]).tolist()
    buffers = {str(n): int((actual[test] > predictions[test]+n).sum()) for n in settings["buffers_min"]}

    fig = plt.figure(figsize=(12, 7.5), layout="constrained")
    upper, lower = fig.subfigures(2, 1)
    a, b = upper.subplots(1, 2)
    c, d = lower.subplots(1, 2, gridspec_kw={"width_ratios": [1.65, 1]})
    names = ["Normal-load", "Reduced-load", "Low-quality observation"]
    colors = ["#2978BD", "#29A79C", "#F08C38"]
    for key, name, color in zip(groups, names, colors):
        mask = test & (states == key)
        a.scatter(actual[mask], predictions[mask], s=16, color=color, edgecolor="white", linewidth=.3,
                  label=f"{name} (n = {int(mask.sum())})")
    a.plot([0, 60], [0, 60], color="#222222", lw=1, label="Identity (y = x)")
    a.set(xlim=(0,60), ylim=(0,60), xlabel="Actual Event Duration (min)", ylabel="Predicted Processing Time (min)")
    a.legend(fontsize=8, loc="upper left")
    a.text(.97,.06,f"Overall MAE  {all_test['mae']:.3f} min\nP90 absolute error  {all_test['p90']:.3f} min\nMean bias  {all_test['bias']:+.3f} min",
           transform=a.transAxes, ha="right", fontsize=8, bbox={"facecolor":"#e9f2f9","edgecolor":"#91aabb"})
    pos = np.arange(len(groups))
    for offset, metric, name, color in [(-.17,"mae","MAE",colors[0]),(.17,"p90","P90 absolute error",colors[2])]:
        bars=b.bar(pos+offset,[g[metric] for g in groups.values()],.34,label=name,color=color)
        b.bar_label(bars,fmt="%.3f",fontsize=8,padding=2)
    b.set_xticks(pos,[f"{name.replace(' observation', chr(10)+'observation')}\n(n = {g['n']})" for name,g in zip(names,groups.values())])
    b.set(ylim=(0,4),ylabel="Error (min)")
    b.legend(loc="upper left",fontsize=8)
    positions = np.arange(len(levels))
    c.fill_between(positions,coverage,40,color="#dcecf9")
    c.plot(positions,coverage,"o-",color=colors[0],mfc="white")
    for i, value in zip(positions, coverage):
        c.annotate(str(value),(i,value),xytext=(0,6),textcoords="offset points",ha="center",fontsize=9)
    c.set(ylim=(40,123),ylabel=f"Covered batches (out of {all_test['n']})",xlabel="Nominal interval coverage level")
    c.set_xticks(list(positions), [f"{p:.0%}" for p in levels])
    d.axis("off")
    d.text(.5,.76,"90% Interval Coverage (by Group)",ha="center",va="center",fontweight="bold")
    d.add_patch(plt.Rectangle((0,.68),1,.16,transform=d.transAxes,fc="#d9e9f6",ec="#708599",zorder=-1))
    grid=d.table(cellText=[[name,f"{g['covered']} / {g['n']}"] for name,g in zip(names,groups.values())],
                 cellLoc="center",bbox=[0,.17,1,.51])
    grid.auto_set_font_size(False); grid.set_fontsize(10)
    for (row,col),cell in grid.get_celld().items():
        cell.set_edgecolor("#708599")
    for ax,title in [(a,"(a)  Predicted Processing Time vs. Actual Duration"),(b,"(b)  Prediction Errors by Group"),(c,"(c)  Interval Coverage Analysis")]:
        ax.set_title(title,fontweight="bold",fontsize=12,pad=9)
    figure("figure_08",fig)
    rank = min(int(cal.sum()), math.ceil((int(cal.sum())+1)*.9))
    table("table_05", ["Parameter","Value","Role in the model"],
          [["Nominal 90% interval",f"{radius:.3f} min on either side of the prediction",
            f"Rank {rank} among {int(cal.sum())} absolute calibration residuals"]],
          caption="Calibration conditions for the batch processing time model.",
          note="Computed calibration row. The other rows describe input settings.")
    return {"fit":int(fit.sum()),"calibration":int(cal.sum()),"test":int(test.sum()),"coefficients":beta.tolist(),
            "overall":all_test,"groups":groups,"coverage":coverage,"radii":radii,"levels":levels,
            "shift_bootstrap_mae_ci95":ci,"window_starts_before_finish":buffers}

