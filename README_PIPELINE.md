# Context-Aware Adaptive EV Routing: test bench

The whole study is one command:

```
python evbench.py run
```

It runs seven stages in order and writes everything to `outputs/`. A live dashboard opens in the browser while it runs (http://localhost:8766): the seven stages lighting up, each answer drawn on a map of its route and chargers next to the referee's plan, the pass rates filling in, and the time and memory each model needs against the edge budget. `outputs/report.html` is the permanent record at the end.

| # | Stage | Input | What happens | Output |
|---|---|---|---|---|
| 1 | inputs | OpenStreetMap Michigan + AFDC charger list | SUMO `netconvert` builds the road network (`build_network.py`); chargers are snapped to roads (`referee/stations.py`). The built network is stored as `data/aa_det.net.xml.xz`, so this is normally just an unzip. | `data/aa_det.net.xml`, `referee/chargers.csv` |
| 2 | validation | Real trips (DEVRT Leaf e+, VED Michigan) | SUMO's energy use is compared with what the real cars measured; the heating/cooling correction is fitted. | `outputs/validation.json` |
| 3 | situations | Road network, chargers | Trips are driven in SUMO, the referee computes every valid plan and the best one, driver wishes are added, 300 test situations are selected. The stored set is checked against its frozen SHA-256. | `referee/cases_v2/test_cases.jsonl` |
| 4 | baselines | Test situations | Random, nearest, rule and exact-planner methods, graded by the referee. | `outputs/test_v2_baselines_summary.csv` |
| 5 | models | Test situations | Qwen2.5 0.5B / 1.5B / 3B answer offline through Ollama, in roles R1, R2, R3-known, R3-full and each wording, then again under the in-car edge profile (4 CPU threads). Each answer records time to decide, tokens/s and model memory. Stops and resumes safely. | `outputs/model_answers.jsonl` |
| 6 | score | Model answers | Every answer graded by the same referee. | `outputs/model_scores.csv`, `outputs/model_scores_summary.csv` |
| 7 | report | All of the above | One HTML page with every table and the fingerprints. | `outputs/report.html` |

Settings: `evbench_config.json` (models, roles, wordings, pilot 40 or all 300, seeds).
Every stage records the SHA-256 of each file it used or made in `outputs/manifest.json`.
Stages 1 to 4 are skipped on the next run when settings and files are unchanged; the model stage only asks what is not answered yet.

```
python evbench.py status              # what is done, with fingerprints
python evbench.py run --from models   # start at a stage
python evbench.py run --only report   # one stage
python evbench.py run --force         # redo everything
python evbench.py dashboard           # look through finished results on the live page (replay)
```

**Edge profiles** (`edge_profiles` in the config): `laptop` uses every CPU core; `in-car` uses 4 threads and checks each model against a budget of 10 s per decision and 4 GB of memory. These budgets are proposed and only change the fits / does not fit label, never the grade. A phone is not measured.

To rebuild the situations from the raw road network instead of using the stored ones, set `"regenerate_situations": true`
(needs `pip install eclipse-sumo`, about 10 to 20 minutes). The report then says whether the rebuilt test set matches the frozen fingerprint.

## Live demo

```
python prototype/demo_server.py
```

Opens a page in the browser. Pick any of the 300 test situations, pick or type the driver's request, pick a model and role, press Ask.
It shows what the model reads, its raw answer, the safety check and retry (R2) or the form and planner (R3), and the referee's verdict next to the best plan.
Without Ollama, "be the model yourself" still lets you choose a plan and have it graded.

## Setup

```
pip install -r requirements.txt
```

Windows step by step: `WINDOWS_GUIDE.md`. Design details: `redesign/SPEC.md`.
