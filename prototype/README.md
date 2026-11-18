# Offline prototype: on-device charging assistant

A minimal, fully offline demo of the thesis idea. A small language model runs on the laptop. It reads a charging
situation and the driver's request and decides whether to charge, where, and to what percentage. An on-device check
catches answers that break a rule the car itself can see and gives the model one more try. The referee's verdict,
computed beforehand in SUMO on the real Michigan road network, then shows whether the decision was right.

Status: implemented and tested against a stand-in model server. Not yet run with a real model.

## Run it (Windows, macOS or Linux)

1. Install Ollama (https://ollama.com/download) and pull a model once: `ollama pull qwen2.5:1.5b`
2. Turn off Wi-Fi if you want to show it is offline.
3. In this folder:

       python app.py                                   # menu of 30 situations
       python app.py --situation 12 --model qwen2.5:3b  # one situation, another model
       python app.py --situation 12 --own               # type your own request
       python app.py --situation 12 --no-verify         # model alone, no check and retry

Only Python 3 is needed (no pip installs).

## What it shows on screen

- The fact sheet and the driver's sentence: exactly what the model reads.
- The model's decision, the time it took on this computer, and the token counts.
- The on-device check: plug fits, charger working and public, enough battery to reach the charger, enough charge to
  arrive above the 10% reserve. If something fails, the reason goes back to the model for one retry.
- The referee: arrival time, cost, battery at the destination, whether every rule was kept (including the driver's
  deadline and budget), and the best option for comparison.

Good situations to demo: 12 (must charge, one charger's plug does not fit, deadline and budget), 16 (must charge,
a charger that is both the wrong plug and out of service), and 8 (an out-of-service charger in the list).

## Limits (say these if asked)

- The 30 situations and their referee answers are precomputed. The laptop does not run SUMO.
- With `--own`, the referee's best answer is still the one for the original request. Your own sentence is only
  checked by the on-device check.
- The on-device check does not check the deadline or the budget, because the car cannot know charging times and prices
  exactly. That is the model's job.

## Files

- `app.py`: the prototype.
- `demo_situations.json`: the 30 pilot situations with fact sheets, the referee's table of every option, and answers.
- `build_demo.py`: rebuilds the JSON from the referee (our side only, needs the referee package).
