# RQ3 fine-tuning (LoRA)

Status: data built and checked (every training answer re-grades as correct with the referee); notebook written but **not yet run**.

1. `python prepare_lora_data.py` writes `lora_train.jsonl` (1,980 chats from 396 Detroit training situations) and
   `lora_val.jsonl` (220 chats from 44 situations kept aside). Already done; the two files are in this folder.
2. Open `lora_train.ipynb` in Google Colab (or Kaggle) with a free T4 GPU. Set `SIZE`, run all cells, download
   `qwen2.5-<size>-ev-lora.gguf`. Repeat for 0.5B, 1.5B and 3B. Time is not measured yet; expect tens of minutes per size.
3. On the experiment laptop, put each `.gguf` next to a file called `Modelfile` containing, for the 1.5B model:

       FROM qwen2.5:1.5b
       ADAPTER ./qwen2.5-1.5b-ev-lora.gguf

   and run `ollama create qwen2.5-ev:1.5b -f Modelfile` (likewise `qwen2.5-ev:0.5b`, `qwen2.5-ev:3b`).
   The adapter sits on top of the same 4-bit model used in every other condition, so only the adapter differs.
4. `python evbench.py run --from models` now also runs the `lora` condition (it is skipped while the `-ev` models are missing).
   In the results the fine-tuned model is listed under its base model name with adaptation `lora`.
