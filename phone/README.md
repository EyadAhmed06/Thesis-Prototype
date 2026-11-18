# RQ5 on a real phone (AWS Device Farm, remote access)

Why not an emulator: an emulator runs on the host computer's processor, so its speed tells us about that computer, not a phone.
Device Farm rents real phones by the minute: $0.17 per device minute after a one-time free trial of 1,000 device minutes
(https://aws.amazon.com/device-farm/pricing/). This measurement should take well under 100 minutes, so it fits in the free trial.
Status: planned; the script is written but has not been run on a phone.

Steps
1. Download the Termux APK from its GitHub releases page (arm64-v8a build).
2. AWS console > Device Farm > Mobile device testing > create a project > Remote access > Start a new session.
   Pick a common mid-range Android phone (write down the model). Wait a minute or two for it to connect.
3. In the session, Upload the Termux APK, open Termux.
4. Type one line (the file must be reachable online, e.g. in the GitHub repo, use the "Raw" link):
       curl -sL https://raw.githubusercontent.com/EyadAhmed06/Thesis-Prototype/main/phone/phone_bench.sh | bash
5. When it finishes (downloads about 3.5 GB of models in total, then benchmarks), take screenshots of the tables and
   end the session. Send the screenshots back; they go into the RQ5 results.

What is measured: tokens per second for reading the prompt (pp1000) and writing the answer (tg60), at 1, 2, 4 and all
cores, and the peak memory of each model. Time per decision = 1000 / read speed + 60 / write speed. Decision quality is not
re-measured on the phone, because the phone runs the same 4-bit model; only speed and memory differ.
Caveat to state in the thesis: the phone uses Qwen's own Q4_K_M files, the laptop uses Ollama's Q4_K_M builds of the same models.
