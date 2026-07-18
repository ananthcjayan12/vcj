# Analyze and improve short script prompts

**Session ID:** ses_08b8be140ffeSxt0yWpWjKqSSO
**Created:** 18/07/2026, 14:29:54
**Updated:** 18/07/2026, 14:33:48

---

## User

@template_lab/prompts/short_script_writing.user.txt @template_lab/prompts/short_candidate_analysis.user.txt @template_lab/prompts/short_script_writing.user.txt @template_lab/prompts/short_script_writing.system.txt can you analyze these prompts and tell me, in the workflow, what resources we are sending along with the prompts? Also, I want you to propose a new prompt structure in such a way that this will be creating more natural and more appealing shorts. This prompt looks very generic.

Ideally, I want you to think like a digital marketer, a winning YouTube short creator, and a very good psychologist, or someone who can create beautiful shorts from a narration. I want you to change the prompts also like that, but before changing the prompts, let me see how you are going to change the prompts. Also, tell me how we are currently sending the prompts, what the payloads are like, and what the other things are that we are giving along with the prompt.

---

## Assistant

I'll trace how these prompts are loaded and what payloads/resources get attached in the short-creation workflow.

**Tool: grep**

**Tool: glob**

**Tool: read**

---

## Assistant

**Tool: read**

**Tool: grep**

**Tool: read**

---

## Assistant

Checking whether user prompt files are used and reviewing schemas/archetypes.

**Tool: grep**

**Tool: read**

**Tool: read**

**Tool: read**

---

## Assistant

## How prompts are sent today

**Important:** the `*.user.txt` files are registered in `prompt_model_mapping.json` but **not read by the pipeline**. Only `*.system.txt` is loaded. The “user” message is a raw `json.dumps(...)` payload.

### Call path
`ShortsPipeline._model_json(task, system_file, user_string)` → `call_model_json(task, system=system_file text, user=user_string, output_schema=...)`

---

### Step 1 — `short_candidate_analysis`

**System:** `short_candidate_analysis.system.txt` only  
**User payload (JSON string):**

```json
{
  "parent_run_id": "...",
  "narration": { /* full narration.json */ },
  "story_skeleton": { /* full story_skeleton.json */ },
  "motion_canvas_manifest": { /* full motion_canvas/manifest.json */ },
  "required_candidate_count": "3-5",
  "deterministic_seed_candidates": [ /* from candidates.analyze() */ ]
}
```

**Also attached (not in prompt text):** JSON **output schema** enforcing candidate shape (archetype, hook, promise, payoff, claim_ids, source_segments, 0–100 scores, warnings).

**Not sent:** `timeline.json` body (only its hash as `source_timeline_id` in seeds), beat/reel TSX, word timestamps, exam syllabus text.

**Seeds** come from deterministic paragraph→hook heuristics in `candidates.py`.

---

### Step 2 — `short_script_writing`

**System:** `short_script_writing.system.txt` only  
**User payload:**

```json
{
  "candidate": { /* selected candidate object */ },
  "parent_narration": { /* full narration.json again */ },
  "required_schema_example": { /* deterministic compile_script() output */ }
}
```

**Not sent:** story skeleton, manifest, timeline, seed list, visual TSX, audio timestamps.  
**No output_schema** on this call — validation is post-hoc via `validate_script`.

**Deterministic seed script** is only: hook → optional reused excerpt → payoff (thin 2–3 lines).

---

### Why it feels generic
- System prompts are 1-line compliance specs, not creative briefs  
- User `.txt` files are dead docs  
- Model is told “return JSON” more than “win the scroll”  
- Seeds teach boring structure (question + excerpt + sentence)  
- No retention psychology, pattern interrupts, open loops, or platform pacing  

---

## Proposed prompt redesign (preview only — not applied)

### Design principles (marketer + Shorts creator + psychology)

| Lever | Application |
|--------|-------------|
| **Pattern interrupt (0–1.5s)** | Visual/verbal anomaly before naming the topic |
| **Open loop** | Promise a payoff the brain must close |
| **One idea, one emotion** | Curiosity / “I was wrong” / exam-power, not textbook calm |
| **Prediction before explanation** | Force micro-commitment (“pause and guess”) |
| **Concrete > abstract** | Objects, numbers, “you” situations |
| **Payoff = rewatchable** | Crisp rule + why intuition failed + optional loop line |
| **No lecture voice** | Spoken cadence, not essay clauses |
| **Reuse as craft, not default** | Exact clause only when it already sounds native on Shorts |

---

### A. `short_candidate_analysis.system.txt` (direction)

**Role:** Senior YouTube Shorts strategist for IGCSE/A-level physics. You do not write full scripts; you pick **moments that can steal attention**.

**Mission:** From one approved lesson, find **3–5 standalone Shorts** that could stop a student mid-scroll. Prefer ideas that create **surprise, contradiction, or prediction**, not “section summaries.”

**Hard constraints (keep current grounding):**
- Ground every claim in supplied claim IDs / paragraphs / reels  
- Reject dependent language (“as we saw earlier”, “in the last chapter”…)  
- ≤2 adjacent reels  
- Single concept per candidate  
- 20–60s target  
- JSON only, schema-compliant  

**Selection psychology (new):**
Score and prefer candidates that have:
1. **Scroll-stop anomaly** — counterintuitive result, missing force, “which is heavier?”, unit trap  
2. **Instant visual** — diagram/motion already in source reels that reads in portrait  
3. **Closed-loop answer** — one sentence the viewer can repeat tomorrow  
4. **Exam bite** — common mark-scheme confusion (mass/weight, resultant force, etc.)  
5. **Standalone** — no prerequisite beyond general school physics  

**Archetype guidance (enrich existing enums):**  
For each archetype, specify *hook energy* (e.g. misconception-bust = “Most students say X. The exam wants Y.”; demo-prediction = “Watch what happens next—then explain it.”).

**Output quality bar:**  
- `hook`: ≤18 words, second-person or concrete image, ends in tension (question or incomplete truth)  
- `promise`: what the viewer gets in one line (not “learn physics”)  
- `payoff`: the *satisfying* close, not a definition dump  
- `working_title`: clickable, not textbook heading  
- Scores: be harsh on `hook_score` if it sounds like a learning objective  

**Process:** Treat `deterministic_seed_candidates` as weak drafts. Rewrite hooks/payoffs aggressively; drop seeds that are “paragraph summaries.”

---

### B. `short_candidate_analysis.user.txt` (make it a real template)

Use as an instruction wrapper the **code should inject** (today it doesn’t):

```text
PARENT RUN: {{parent_run_id}}
GOAL: 3–5 Short candidates optimized for retention, not completeness.

ARTIFACTS (immutable ground truth):
- narration.json
- story_skeleton.json  
- motion_canvas_manifest.json
- deterministic_seed_candidates (optional starting points only)

RULES REMINDER:
- Every claim_id must exist in narration/story
- Prefer moments with strong visual_reuse_score potential
- Flag warnings when audio reuse would force dull lecture cadence

Return candidates ranked by true scroll-stopping potential (overall_score).
```

**Payload shape recommendation (code change later):** slim artifacts instead of full dumps when possible:
- paragraphs with `id`, `text`, `claim_ids`  
- beats with ids + one-line intent  
- reels with id, start/end, title/summary  
- seeds  

Full blobs burn tokens and bury the creative signal.

---

### C. `short_script_writing.system.txt` (direction)

**Role:** You write **spoken** physics Shorts that feel like a sharp creator, not a textbook TTS.

**Format (fixed emotional arc, flexible line count):**

| Beat | Time feel | Job |
|------|-----------|-----|
| **Hook** | 0–3s | Pattern interrupt + open loop |
| **Context** | 2–5s | One concrete setup (who/what/where) |
| **Tension** | 3–8s | Prediction, false belief, or “wait…” |
| **Explanation** | middle | One mechanism; short sentences; one formula max if needed |
| **Payoff** | last 4–8s | Close the loop; restate in plain language |
| **Loop (optional)** | last line | Cold-open echo or “now rewatch the motion” — never “follow for more” |

**Voice rules:**
- Max ~170 spoken words; aim **90–140** for punch  
- Prefer contractions, active voice, “you”  
- No “In this video we will…” / “Today we learn…”  
- One concept only  
- If you use a number or formula, make it *earn* the payoff  
- **Reuse lines:** copy one exact contiguous clause only; if it sounds essay-like, `generate` instead  
- Each line: `visual_intent` that a portrait editor can shoot (face-of-diagram, arrow slam, before/after split, freeze-frame question)

**Psychology micro-tactics (pick 1–2 per Short, not all):**
- False consensus: “Everyone thinks…”  
- Binary choice: “A or B?”  
- Status: “This is the line that gets the mark”  
- Embodied: “Imagine you’re the skydiver…”  
- Reveal delay: name the answer only after the tension line  

**Anti-patterns to ban:**
- Hook that restates the lesson title  
- Explanation that starts with definition before stakes  
- Payoff that introduces a second topic  
- Soft CTA spam  

**Grounding:** preserve candidate `claim_ids`; map lines to claims; JSON only matching schema example.

---

### D. `short_script_writing.user.txt` (real template)

```text
Compile ONE Short from the selected candidate.

CANDIDATE (creative north star):
{{candidate}}

PARENT NARRATION (only source of reusable clauses + claim truth):
{{parent_narration paragraphs filtered to candidate source_paragraph_ids + neighbors if needed}}

SCHEMA EXAMPLE (structure/fields only — improve the writing dramatically):
{{required_schema_example}}

Deliver a script that would beat a generic educational Short on retention.
Prioritize: hook sharpness > natural speech > exact audio reuse.
```

**Payload recommendation:**
- Pass **filtered** paragraphs (source + maybe ±1), not entire lesson  
- Add optional `voice_profile`: `{ "energy": "curious_challenger", "audience": "IGCSE_student", "ban_words": [...] }`  
- Add `platform_notes`: 9:16, captions on, first line must work muted as on-screen text  

---

### E. Optional third “creative director” fields (schema-friendly)

Without breaking validators, you can ask models to fill richer text inside existing fields:
- `hook` / `payoff` / `promise` carry the psychology  
- `warnings` for “weak visual”, “lecture-y source audio”  
- Later: extend script lines with `role`: `context` | `tension` (validators already allow roles beyond hook/payoff as long as hook + payoff exist)

---

### F. What I would change in code (when you approve)

1. **Actually load** `*.user.txt` and fill placeholders; stop treating user prompts as dead files  
2. **Slim JSON payloads** (filter narration; summarize manifest)  
3. **Stronger seed scripts** in `compile_script`: 5-beat skeleton so the model doesn’t learn 3-line mediocrity  
4. **output_schema** for script writing (parity with candidates)  
5. Candidate prompt: instruct “seeds are low-quality; rewrite hooks”  

---

## Summary

| Stage | System | User message today | Extra |
|--------|--------|-------------------|--------|
| Candidate analysis | 1-line system file | Full narration + story + manifest + seeds JSON | Strict output schema |
| Script writing | 1-line system file | candidate + full narration + thin schema example | Post-validate only |
| User `.txt` files | — | **Unused** | Listed in mapping only |

I have **not** edited the prompt files yet. If this direction looks right, next step is rewrite the four prompt files (and optionally wire user templates + slimmer payloads in `pipeline.py`).

---

## User

My doubt is: why are we sending this deterministic seed candidate? The problem I am facing is that if we are sending some predefined candidates directly, after analysis I am only getting the same kind of candidate. Is it because of that? I don't want to need to predetermine something. Ideally, the AI only should find something. ?

---

## Assistant

Yes. Seeds are the main reason you’re getting the same candidates.

**Tool: read**

**Tool: grep**

---

## Assistant

**Yes — the seeds are a big reason you keep seeing the same candidates.**

### Why seeds exist
They were built as a **fallback / bootstrap**:
1. **`use_model=False`** → only `candidates.analyze()` runs (no AI).
2. **Cost estimate** → needs a sample output shape.
3. **Original intent** → “give the model a starting point so JSON shape is easier.”

They were **not** meant to be the creative source of truth. The system prompt never says “ignore or rewrite seeds,” so the model treats them as the answer key.

### What the seeds actually do
`candidates.py` is mechanical:
- first ~5 **paragraphs** → one candidate each  
- hook = first `?` in text, else `"Can you predict the physics behind this: {first sentence}?"`  
- payoff = first sentence  
- archetype cycles a fixed list  
- scores are mostly hardcoded (~75–85)

So every run of the same lesson produces **almost the same 3–5 ideas**. When that list is stuffed into the user JSON as `deterministic_seed_candidates`, the model is heavily anchored: it lightly edits titles/hooks instead of hunting new moments in the lesson.

### Is the AI “only finding things”?
**No, not today.** Flow is:

```
deterministic seeds  →  (optional) model “enhance”  →  validate
```

not:

```
raw lesson artifacts  →  model discovers candidates
```

With a 1-line system prompt and a full seed list in-context, discovery loses to **copy-the-seeds**.

### What you should do (recommended)
**Stop sending seed candidates into the model prompt.**  
Keep deterministic analysis only for:
- offline/no-model mode  
- maybe cost estimation  

For model mode, send only ground truth:
- narration (or slim paragraphs + claims)
- story skeleton / beats
- manifest reels
- constraints + output schema

And in the system prompt, explicitly: **discover from artifacts; do not receive or imitate pre-made candidates.**

Optional middle ground (usually worse than pure discovery): send seeds labeled `negative_examples` / “do not copy structure” — still risks anchoring. Cleanest is **no seeds in the model call**.

### Bottom line
| Mode | Who picks ideas |
|------|------------------|
| `use_model=False` | Code only (same every time) |
| `use_model=True` today | Code first, model polishes → **feels predetermined** |
| What you want | **Model only** from lesson artifacts; seeds out of the prompt |

I have not changed code yet. If you want, next step is remove `deterministic_seed_candidates` from the analyze model payload and tighten the candidate system prompt for pure discovery.

---

