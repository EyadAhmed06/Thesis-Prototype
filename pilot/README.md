# Laptop pilot: small models on 30 charging situations

What this does: asks three small Qwen2.5 models (0.5B, 1.5B, 3B, 4-bit) to make the charging decision for 30
situations from the test set (15 must charge, 15 do not, spread over all difficulty groups). The model sees only the
fact sheet and the driver's sentence. Nothing is scored on the laptop; the answers come back to us for the referee.

It needs about 4 GB of free disk and runs on CPU. On the i7-13700H laptop expect roughly 1 to 3 hours in total.

## Steps (Windows 11)

1. Install Ollama from https://ollama.com/download and start it (it runs in the tray).
2. Open PowerShell in this folder and download the models (one time):

       ollama pull qwen2.5:0.5b
       ollama pull qwen2.5:1.5b
       ollama pull qwen2.5:3b

3. Quick check (5 situations, smallest model, about a minute):

       python run_pilot.py --models qwen2.5:0.5b --limit 5 --out check.jsonl

4. The real pilot, two conditions. Close other heavy apps and keep the laptop plugged in.

       python run_pilot.py --facts with_energy --out pilot_results.jsonl
       python run_pilot.py --facts without_energy --out pilot_results.jsonl

5. Send back `pilot_results.jsonl`. Also note the laptop model, RAM and whether it was on power.

The script needs only Python 3 (no pip installs). Results are appended, so a stopped run can be restarted;
duplicate lines are removed when scoring.

## Files

- `run_pilot.py`: the runner (R1: the model decides alone).
- `pilot_cases.jsonl`: the 30 situations, without the answers.
- `score_pilot.py`: our side only, grades the returned file against the referee.

## Optional third run (R3: the model only reads the driver's sentence)

    python run_pilot.py --role R3 --out pilot_results.jsonl

Here the model only turns the sentence into goal, deadline and budget; a fixed planner then decides. This is short
(the prompt is one sentence), so it takes a few minutes.
