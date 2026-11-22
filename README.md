# Cross-layer graph reasoning for production planning and local replanning

This package accompanies *A digital twin framework for intelligent production control through cross-layer graph reasoning*. The experiments read the supplied inputs in `Data/`, compute and verify plans, and write results to `outputs/`. Section 5.1 and Appendix A of the paper describe the controlled hot-rolling cases and their scope.

## Run on Windows

Use Python 3.11 and Node.js 22. Node.js executes the full-line scheduler. From this directory, run the following commands in PowerShell. A virtual environment is optional.

```powershell
python -m pip install -r requirements.txt
python Main.py --mode validate
python Main.py --mode demo
```

For all external benchmark results, also install PyTorch 2.5.1 with a build appropriate for your CPU or GPU. The resource installer downloads the official ReSched inference module and pretrained policy and the GTool evaluation corpus. It checks each published dependency against the pinned release used for evaluation. The runtime files stay under the ignored project-local directory `.benchmark-runtime/`.

```powershell
python -m pip install torch==2.5.1
python -m benchmark_resources
python Main.py --mode validate
python Main.py --mode comparison
python Main.py --mode ablation
```

Check the three resource flags printed by `validate` before a full benchmark run. A run without installed benchmark resources computes the available methods and identifies the affected evaluations in `limited_resources`. Re-running a mode replaces its output with that run's results, including any unavailable benchmark columns. With the dependencies installed, evaluation runs offline. Use `--device cpu` to select the single-thread CPU ReSched control, or `--device cuda` to request CUDA. The default is `auto`. The combinatorial solvers, statistical estimates and drawing routines use the CPU.

## Generate and check the figures and tables

```powershell
python Main.py --mode figures
python Main.py --mode tables
python Main.py --mode validate_figures
python Main.py --mode validate_tables
```

| Entry | Scope |
| --- | --- |
| `help` | List the public modes and device option. |
| `validate` | Check local dependencies, controlled case counts, and external resource availability. |
| `demo` | Solve and verify one planning case, one paired execution event, and one public scheduling instance. |
| `comparison` | Run controlled and public benchmarks and fit the held-out duration model. |
| `ablation` | Vary search checks, neighborhood policies, forecast tolerance and input expiry. Compare hitting-set policies and evaluate port reordering on the public split when installed. |
| `figures` | Recompute the evidence for Figures 5–12 and render result panels as PNG and SVG. |
| `tables` | Run the relevant comparison and ablation experiments and write CSV and Markdown from the same rows. |
| `validate_figures`, `validate_tables` | Check the run receipts, file integrity, figure structure and resolution, or table dimensions and exact CSV–Markdown cell agreement. |

## Inputs, methods and outputs

| Location | Contents |
| --- | --- |
| `Data/` | Processing records, weighted conflict graphs and public benchmark inputs. The predictor reads decision-time features and uses the recorded duration for fitting or scoring. |
| `Data/full_line.json` | Line operating conditions, stand and port records, maintenance jobs and crew reservations for the baseline and feedback case. |
| `Data/planning/`, `Data/replanning/` | Initial cases, paired before/after states, execution snapshots and expiry calendars. Each method reads the applicable states and computes its own plans and verification outcomes. |
| `planning.py`, `replanning.py` | Budgeted candidate search, independent feasibility checks, downstream reuse tests, reservation repair and paired evaluation. |
| `calibration.py`, `conflicts.py` | Shift-disjoint fitting, conformal interval calibration, cluster bootstrap, conflict cover and exhaustive cost checks. |
| `line_solver.js`, `full_line.py` | Baseline and updated scheduling on the full line, together with an independent crew-overlap matrix. |
| `benchmarks.py`, `benchmark_lib/` | Flexible job-shop scheduling, retrieval, port reordering, manufacturing-cell and coil sequencing benchmarks. Third-party notices accompany the benchmark inputs. |
| `config.json`, `artifact_specs.json` | Rendering and calibration settings, figure panels and table dimensions. The solver constants for the original experiments are retained in their respective modules. |
| `outputs/figures/`, `outputs/tables/` | Figures 5–12 and the result portions of Tables 2, 3, 5 and 10–16. Table 2 has two independently readable sections. |
| `outputs/<mode>/summary.json` | Run ID, execution time, resource coverage and aggregate results. Individual predictions are held in memory only while evaluating or drawing the corresponding figure. |
| `outputs/validation/` | Run receipts and structural checks. The two release reports record the separate comparison to the manuscript. |

The initial search benchmark holds candidate tasks fixed. It measures solver behavior after candidate generation. The timings exclude language-model inference. Whole-graph feasibility and correct downstream reuse are evaluated separately. Table 10 distinguishes computations supported by this package from comparisons quoted in the literature. The package keeps required third-party notices in `Data/benchmarks/NOTICES.md` and `benchmark_lib/`.

See `PUBLIC_RELEASE_REPORT.md` for execution conditions, and `PUBLIC_FIGURE_TABLE_REPORT.md` for figure-by-figure and table-by-table agreement.

