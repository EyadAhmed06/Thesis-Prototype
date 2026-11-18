# Core redesign: spec (agreed by yousi 2026-11-17, option "Core redesign (points 1-4)")
Written BEFORE any code or model run. Changes after a model has run must be listed in a changelog at the end.

## 1. Driver wishes (gradable from the referee's options table, no new SUMO runs)
| id | words (example) | condition on a charging option | no-charge option | seen in training? |
|---|---|---|---|---|
| max_wait | "I can't spend more than 40 minutes at a charger" | 5 min + charging minutes <= X | passes | yes |
| avoid_network | "My card doesn't work with ChargePoint" | charger network != N | passes | yes |
| min_arrival | "I need at least 40% left when I arrive" | battery at destination >= X | battery at destination >= X | yes |
| parked_at | "I have a call at 15:00 and want to be parked then" | stop start <= T <= stop end | fails | no (test only) |
| free_only | "Only use free chargers" | charging cost == 0 | passes | no (test only) |
| stop_city | "I'd like to stop in Livonia for lunch" | charger city == C | fails | no (test only) |
| no_fast | "I'd rather not use fast chargers" | charger is Level 2 | passes | no (test only) |
Each situation has 0, 1 or 2 wishes. Wish parameters are set from the options so a wish usually changes the answer
(the unconstrained best breaks it), never by hand.

## 2. Priority order when not everything can be kept (conflict situations)
Hard, never allowed: plug fits, working, public, battery >= 10% at charger and at destination.
Then, in order: deadline > budget > wishes. Best = safe option with the fewest broken rules in that order
(lexicographic: deadline broken?, budget broken?, number of wishes broken), then the goal (fastest/cheapest).
The model must also say which requests it gives up ("gives_up"). The driver's request says the priority order in words.

## 3. Wording levels
template (fixed sentences) | paraphrase (written by a different LLM, checked by script that numbers survive) |
human (~50 written by people who never saw the templates). Same situations, same correct answers.

## 4. Roles
R1 decide alone; R2 decide + on-device safety check + one retry; R3-known: model fills a form with goal, deadline, budget,
the 3 training wish types and free-text "other", then a fixed planner decides (cannot act on "other");
R3-full: form covers all 6 wish types (an upper bound for the reading-only approach).

## 5. Grading
pass = safe and breaks nothing that the best option keeps (same violation level as the best).
honest = gives_up matches the rules the decision actually breaks. Plus top-1, target error, gap as before.
Breakdowns: wish type, held-out vs seen wish, wording level, conflict, trap, n rules.

## 6. Credibility
Test set frozen (file hash recorded) before any model run. Analysis plan = this file. Eyad hand-checks 30 referee answers.
Train (Detroit) never used for grading; held-out wish types never appear in training prompts.

## Changelog (all before any model run)
- 2026-11-17: added held-out wish no_fast ("no DC fast chargers"), because free_only can only appear where a free usable charger exists (22 test situations).
- 2026-11-17: R3 planner = exact planner (searches every option with the referee's rules, using only fact-sheet numbers). With a correct reading it matches the referee, so R3's score measures reading only. Strongest possible reading-only opponent.
- 2026-11-17: to give rare wish types enough situations, SUMO drove 2,800 more Ann Arbor trips (seed 31, ids test2000+); test pool 3,180 solvable -> 1,717 robust with wishes -> 300 kept (100 conflict).
- 2026-11-17: some two-rule drivers (40%) get a budget below every on-time option, so the deadline-over-budget priority is tested (26 situations).
- 2026-11-17: test set frozen, sha256 in referee/cases_v2/FROZEN_test_v2.json.
- 2026-11-17 (found while proof-reading requests, before any model run): parked_at now means "not driving at time T", so before leaving, during the stop or after arriving all count; T is always set while the best option is still driving. no_fast worded as a firm request ("Please don't use fast chargers"). Test and training sets rebuilt and re-frozen (new sha256).
- 2026-11-17: paraphrase level written by Claude (a different model family from the Qwen models tested), checked by script that every time, amount, percentage, minutes, city and network survive and the goal direction is kept. Done for 150 situations (redesign/paraphrases_pilot.tsv: the 40 pilot ones; paraphrases_batch2.tsv: 110 more), all 150 pass the check.

## Changelog 2026-11-18: edge profiles (proposed) and live dashboard
- Every model answer now records time to decide (including the R2 retry), Ollama's own reading and writing speed (tokens/s) and the memory of the loaded model (Ollama /api/ps).
- Edge profiles in evbench_config.json: "laptop" (all CPU cores) and "in-car" (4 CPU threads; budget 10 s per decision and 4 GB model memory). The in-car budgets are PROPOSED, not agreed; they only change the fits / does not fit label, never the grading. The extra profile runs only roles R2 and R3-known with template wording.
- Phone and battery energy are not measured.
- Display only (not graded, not hashed): referee/cases_v2/test_maps.json from referee/make_maps.py; live dashboard (live.py, ui/); demo restyled.
