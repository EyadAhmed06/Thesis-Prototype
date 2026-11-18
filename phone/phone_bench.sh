#!/data/data/com.termux/files/usr/bin/bash
# RQ5 on a real Android phone: how long one charging decision takes and how much memory the model needs.
# Runs inside Termux (install Termux from F-Droid or its GitHub releases, not the Play Store).
# One line to start it in Termux:   curl -sL <raw URL of this file> | bash
# It measures the same work as one decision in the study: reading about 1,000 tokens (instruction, fact sheet,
# request) and writing about 60 tokens of JSON, with the same 4-bit (Q4_K_M) Qwen2.5 models, using llama.cpp.
# Status: written, NOT yet run on a phone.
set -e
pkg update -y >/dev/null 2>&1 || true
pkg install -y llama-cpp wget time >/dev/null
mkdir -p ~/evbench && cd ~/evbench
echo "device: $(getprop ro.product.manufacturer) $(getprop ro.product.model), Android $(getprop ro.build.version.release), chip $(getprop ro.soc.model) $(getprop ro.board.platform)"
echo "memory: $(grep MemTotal /proc/meminfo)"; echo "cores: $(nproc)"
for SIZE in 0.5b 1.5b 3b; do
  F=qwen2.5-${SIZE}-instruct-q4_k_m.gguf
  REPO=Qwen2.5-$(echo $SIZE | tr b B)-Instruct-GGUF
  [ -f $F ] || wget -q --show-progress https://huggingface.co/Qwen/$REPO/resolve/main/$F
  echo "== $SIZE ($(du -m $F | cut -f1) MB)"
  # p = prompt tokens read, n = tokens written, t = CPU threads (1, 2, 4 and all cores), r = 3 repetitions
  command time -f "peak memory: %M KB" llama-bench -m $F -p 1000 -n 60 -t 1,2,4,$(nproc) -r 3 -o md 2>&1 | grep -v "^ggml\|^llama_\|^load" | tee -a results_$SIZE.md
done
echo "Done. Take a screenshot of the tables above (or copy ~/evbench/results_*.md) and send them back."
