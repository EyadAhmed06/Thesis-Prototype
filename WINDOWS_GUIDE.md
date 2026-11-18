# Running the study on Windows, step by step

Written for the experiment laptop (ASUS Vivobook, Windows 11, no graphics card). Every step is copy and paste.

## Once: install the tools (about 15 minutes)

1. **Python.** Install Python 3.12 or newer from https://www.python.org/downloads/ . On the first screen tick **"Add python.exe to PATH"**.
2. **Ollama.** Install from https://ollama.com/download . It starts by itself and shows a llama icon near the clock.
3. **The code.** On the GitHub page of the repository press **Code → Download ZIP**, and unzip it, for example to `C:\thesis`.
   (Or with Git: `git clone <repository URL> C:\thesis`.)
4. Open **PowerShell** (Start menu, type PowerShell) and run:

```
cd C:\thesis
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen2.5:0.5b
ollama pull qwen2.5:1.5b
ollama pull qwen2.5:3b
```

If PowerShell refuses to run `activate`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and answer `Y`.
The three models are about 0.4, 1.0 and 1.9 GB.

## Each time: run the study

```
cd C:\thesis
.venv\Scripts\activate
python evbench.py run
```

- A page opens in the browser and shows the run live (http://localhost:8766). Leave it open; it is a nice thing to show.
- The first four stages take about one minute. The model stage takes the longest: it prints each answer and how many minutes are left.
- You can close the window or stop with **Ctrl+C** at any time. Running `python evbench.py run` again continues where it stopped; nothing is asked twice.
- Keep the laptop plugged in and stop it going to sleep (Settings → System → Power → Sleep: Never) during long runs.
- For timing results that are fair, close other programs while the models run (the edge numbers are measured on this laptop). The live page itself uses a little CPU, so for the final timing run use `python evbench.py run --no-dashboard` and look at the results afterwards with `python evbench.py dashboard`.

At the end, open `C:\thesis\outputs\report.html` (double-click it). To look through the answers again later on the live page: `python evbench.py dashboard`.

**To send the results back:** zip the `outputs` folder and share it. It holds every answer, the scores and the fingerprints.

## Pilot first, then everything

`evbench_config.json` says `"models_on": "pilot"`, which runs the 40 pilot situations: 960 answers on the full laptop, plus 240 more with the in-car profile (4 CPU threads).
After the pilot looks right, change it to `"models_on": "all"` and run `python evbench.py run` again; only the new answers are asked.

## The live demo (for showing the supervisors)

```
cd C:\thesis
.venv\Scripts\activate
python prototype\demo_server.py
```

The browser opens at http://localhost:8765 . Turn Wi-Fi off first to show it runs offline. Stop it with Ctrl+C.

## If something goes wrong

| Message | What to do |
|---|---|
| `'python' is not recognized` | Python was installed without "Add to PATH". Reinstall and tick it. |
| `Ollama is not running` | Start Ollama from the Start menu, wait 10 seconds, run again. |
| `models not downloaded yet: ollama pull ...` | Run the `ollama pull` command it prints. |
| `test set does not match its frozen fingerprint` | A file in `referee/cases_v2` changed. Download the code again; do not edit those files. |
| Anything else | Copy the last 20 lines of the window and send them. |
