"""RQ3 adaptation conditions for the model runner (standard library only, so it runs on the laptop as is).

  none      the plain instruction (the runner's SYSTEM prompt)
  rules     the same instruction plus a step-by-step description of how to check a decision (a richer system prompt)
  examples  the plain instruction plus 2 worked examples retrieved for each request from the Detroit training situations
  lora      the plain instruction, sent to a fine-tuned model (an Ollama model with a LoRA adapter, see lora/)

Only training situations are ever shown or retrieved; they contain only the three training wish types, so the test
still measures whether a gain carries over to new roads and to new kinds of wishes. Retrieval looks only at the words
of the driver's request (TF-IDF cosine similarity), never at the test situation's answer or labels."""
import json, math, os, re
from collections import Counter

ADAPTS = ('none', 'rules', 'examples', 'lora')
N_EXAMPLES = 2          # two worked examples per request
CTX_EXAMPLES = 4096     # same context window as the other conditions; two examples come to about 2,200 tokens at most on the test set (estimated as characters / 4), so they fit

RULES = ("\n\nHow to check a decision, step by step:\n"
         "1. Battery when you reach a charger = battery now minus the energy to reach it. It must stay at or above the reserve.\n"
         "2. Battery at the destination = the percentage you charge to minus the energy from the charger to the destination. "
         "It must be at or above the reserve.\n"
         "3. Energy added = (target percentage minus battery at the charger) times the usable capacity. Time at the charger = "
         "5 minutes plus the charging time (energy divided by the charger's power; DC fast chargers slow down above 80%). "
         "Cost = energy times the price per kWh, or hours charging times the price per hour.\n"
         "4. Arrival time = time now + minutes to the charger + time at the charger + minutes from the charger to the destination.\n"
         "5. Check every request of the driver against the decision: where you stop, which network and kind of charger you use, "
         "how long the stop takes, what it costs, when you are driving, and how much battery you arrive with.\n"
         "6. If the trip fits without charging and nothing the driver asks for needs a stop, do not charge.\n"
         "7. Charge only as much as needed: the smallest target that keeps everything you can keep.")

RULES_R3 = ("\nField meanings: goal is fastest if the driver mainly wants to arrive early, cheapest if they mainly want to pay little; "
            "deadline is the latest arrival time; budget is the most they will pay for charging; every other field is a wish the driver "
            "states. Copy numbers, times, cities and network names exactly as the driver says them.")

def _hhmm(m): m = int(round(m)); return f'{m // 60:02d}:{m % 60:02d}'

def answer_json(c):
    """The correct decision of a training situation, in the exact format the model must answer in."""
    ch = bool(c['must_charge'])
    return json.dumps({"charge": ch, "charger": c['best_letter'] if ch else None,
                       "target_percent": int(round(100 * c['best_target'])) if ch else None, "gives_up": list(c.get('gives_up') or [])})

def form_json(c, full=False):
    """The correct R3 form of a training situation (training situations only have the three training wish types)."""
    f = {"goal": c['goal'], "deadline": _hhmm(c['deadline_min']) if c.get('deadline_min') is not None else None,
         "budget": c.get('budget'), "max_wait_minutes": None, "avoid_network": None, "min_arrival_percent": None}
    if full: f.update(parked_at=None, free_only=False, stop_city=None, no_fast=False)
    for w in c.get('wishes', []):
        if w['type'] == 'max_wait': f['max_wait_minutes'] = w['value']
        if w['type'] == 'avoid_network': f['avoid_network'] = str(w['value']).replace(' Network', '')
        if w['type'] == 'min_arrival': f['min_arrival_percent'] = int(round(100 * w['value']))
    f['other'] = None
    return json.dumps(f)

_tok = lambda s: re.findall(r"[a-z0-9$:%.]+", s.lower())

class Retriever:
    """TF-IDF over the words of the training requests; returns the most similar training situations."""
    def __init__(self, train_path):
        self.cases = [json.loads(l) for l in open(train_path, encoding='utf-8')]
        docs = [_tok(' '.join(c['requests']['template'])) for c in self.cases]
        df = Counter(t for d in docs for t in set(d)); n = len(docs)
        self.idf = {t: math.log((1 + n) / (1 + k)) + 1 for t, k in df.items()}
        self.vecs = [self._vec(d) for d in docs]
    def _vec(self, toks):
        tf = Counter(toks); v = {t: k * self.idf.get(t, 0.0) for t, k in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}
    def top(self, text, k=N_EXAMPLES):
        q = self._vec(_tok(text))
        sims = [(sum(w * v.get(t, 0.0) for t, w in q.items()), i) for i, v in enumerate(self.vecs)]
        return [self.cases[i] for _, i in sorted(sims, key=lambda x: (-x[0], x[1]))[:k]]

def example_messages(retr, req, role, facts, full=False):
    """Worked examples as earlier chat turns: the request (and fact sheet) and the correct answer."""
    out = []; picked = retr.top(req)
    for c in picked:
        ex_req = c['requests']['template'][0]
        if role.startswith('R3'):
            out += [{"role": "user", "content": f'Driver says: "{ex_req}"'}, {"role": "assistant", "content": form_json(c, full)}]
        else:
            out += [{"role": "user", "content": c['facts'][facts] + f'\n\nDriver says: "{ex_req}"'},
                    {"role": "assistant", "content": answer_json(c)}]
    return out, [c['id'] for c in picked]

LORA_SUFFIX = '-ev'   # fine-tuned models are named like the base model plus this suffix, e.g. qwen2.5-ev:1.5b
def base_name(tag):
    """qwen2.5-ev:1.5b -> qwen2.5:1.5b, so a fine-tuned model is compared with its own base model."""
    name, _, size = tag.partition(':')
    return (name[:-len(LORA_SUFFIX)] if name.endswith(LORA_SUFFIX) else name) + (':' + size if size else '')
def lora_name(tag):
    name, _, size = tag.partition(':')
    return name + LORA_SUFFIX + (':' + size if size else '')

def default_train_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'referee', 'cases_v2', 'train_cases.jsonl')
