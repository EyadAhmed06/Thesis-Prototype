# Pilot, version 2 (driver wishes and conflicts)
1. Install Ollama, then `ollama pull qwen2.5:0.5b`, `qwen2.5:1.5b`, `qwen2.5:3b`.
2. In this folder run each role once (40 situations each):
```
python run_pilot_v2.py --role R1
python run_pilot_v2.py --role R2
python run_pilot_v2.py --role R3-known
python run_pilot_v2.py --role R3-full
# then the same four again with --wording paraphrase
```
3. Send back `pilot_v2_results.jsonl`.
Human requests: open `human_requests_sheet.csv`, and in the last column write, in your own words, how you would ask the car
for exactly what the row says (goal, arrival time, budget, wishes). Please don't look at the other templates first.
