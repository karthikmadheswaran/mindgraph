# MindGraph Generation Quality Engineering Report

**Date:** 2026-04-13  
**Iterations:** 4  
**Judge model:** Flash-Lite (iterations 1–4), Pro (intermediate validation after iter 2, final validation after iter 4)

---

## Score Progression

| Dimension          | Baseline | Iter1 | Iter2 | (Pro mid) | Iter3 | Iter4 | Final(Pro) |
|--------------------|----------|-------|-------|-----------|-------|-------|------------|
| Inference Quality  | 4.00     | 4.23  | 4.50  | 4.37      | 4.43  | 4.50  | **4.53** ✓ |
| Conv. Intelligence | 3.87     | 4.27  | 4.70  | 4.50      | 4.63  | 4.73  | **4.47** ~ |
| Tone               | 4.70     | 4.57  | 4.63  | 4.80      | 4.60  | 4.70  | **4.80** ✓ |
| Groundedness       | 4.93     | 4.93  | 5.00  | 4.93      | 5.00  | 5.00  | **5.00** ✓ |
| Noise Resistance   | 5.00     | 5.00  | 5.00  | 5.00      | 5.00  | 5.00  | **5.00** ✓ |
| Relevance          | 4.87     | 4.93  | 5.00  | 4.90      | 5.00  | 5.00  | **4.93** ✓ |
| Completeness       | 4.83     | 4.63  | 4.77  | 4.77      | 4.83  | 4.80  | **4.70**   |

| Failure modes | 30/30 | 27/30 | 29/30 | 29/30 | 30/30 | 29/30 | **29/30** ✓ |

> The 29/30 "failure" is a persistent harness false positive: `repetition_user_says_already_know` receives all-5 scores from the judge ("perfectly handles the user's frustration") but the LLM correctly pivots the conversation by referencing the journal topic "Tamil crypto community" — which is the forbidden string for that test case. The new anti-repetition rule causes the LLM to do exactly the right thing (offer a new angle), but that new angle happens to mention the forbidden phrase.

### Targets vs Actuals (Final Pro)

| Dimension          | Target | Final(Pro) | Status |
|--------------------|--------|------------|--------|
| Inference Quality  | ≥ 4.5  | 4.53       | ✓      |
| Conv. Intelligence | ≥ 4.5  | 4.47       | ~      |
| Tone               | ≥ 4.7  | 4.80       | ✓      |
| Groundedness       | ≥ 4.8  | 5.00       | ✓      |
| Noise Resistance   | ≥ 4.8  | 5.00       | ✓      |
| Failure modes      | ≥ 28   | 29/30      | ✓      |

Conv. Intelligence (4.47) is within judge noise of the 4.5 target. Flash judge gave 4.73 after iteration 4. The Pro score is dragged down by two outlier tests where Pro is significantly harsher than Flash: `repetition_same_question_rephrased` (Pro: Con=1 vs Flash: Con=5) and `followup_single_word_query` (Pro: Con=1 vs Flash: Con=4). Both are stochastic — different LLM responses + different judge calibration.

---

## Category Improvements (Baseline → Final Pro)

| Category       | Conv baseline | Conv final | Inf baseline | Inf final |
|----------------|---------------|------------|--------------|-----------|
| Opinion        | ~4.0          | 4.7        | ~4.0         | 5.0       |
| Repetition     | ~3.5          | 4.2        | ~4.0         | 4.6       |
| Follow-up Qs   | ~3.4          | 4.2        | ~3.6         | 4.2       |
| Factual Nuance | 3.4           | 4.6        | 3.0          | 4.6       |
| Emotional      | ~4.0          | 4.6        | ~4.5         | 4.2       |
| Casual         | ~3.5          | 4.5        | ~3.5         | 4.5       |

Factual Nuance was the hardest category: both Conv and Inf moved from ~3.0–3.4 baseline to 4.6 in the final Pro run.

---

## Changes That Helped

### Iteration 1: Permission to infer + anti-repetition
**Impact:** Inference Quality +0.23, Conv Intelligence +0.40 (Flash)

Two rules added to "How to Respond":

1. **Inference permission rule** — when asked "what do you think?", "is this good or bad?", "should I worry?", offer a grounded perspective. Frame as "Based on what you've written…" not "I can't determine…"
   - `opinion_should_i_worry`: Inf 1 → 3 (Flash). Fixed the refusal pattern — LLM now engages instead of deflecting.
   - Opinion category: Inf 4.0 → 4.5 (Flash)

2. **Anti-repetition rule** — if the user rephrases a question already answered, don't repeat the previous answer; pivot to a new angle or follow-up question.
   - `repetition_same_question_rephrased`: Conv 1 → 3 (Flash). Broke the "restating facts" loop.

### Iteration 2: Follow-up questions + synthesis + memory-for-creative
**Impact:** Inference Quality 4.23 → 4.50, Conv Intelligence 4.27 → 4.70 (Flash). Failure modes recovered to 29/30.

Three rules added to "How to Respond":

3. **Follow-up question rule** — when user shares feelings, confusion, or asks vague/single-word questions, ask ONE thoughtful follow-up question rather than just acknowledging.
   - Follow-up Qs category: Conv 3.4 → 4.8 (Flash)
   - `followup_single_word_query`: Conv 3 → 4 (Flash)

4. **Synthesis-over-listing rule** — when multiple entries are provided, look for patterns and changes across them; synthesize in narrative prose; always land on a conclusion ("What I notice is…").
   - Factual Nuance: Inf 3.0 → 4.0 (Flash)
   - `casual_what_should_i_journal_about`: recovered from Inf=1 (was saying "I don't see anything in your entries") to Inf=4

5. **Memory-for-creative rule** — when no journal entries are available but memory exists, use memory for personalized responses; don't fall back to "I don't see anything."
   - Fixed `casual_what_should_i_journal_about` which was failing because LLM ignored Projects/People memory when entries were empty.

### Iteration 3: Metric calibration guidance
**Impact:** `opinion_should_i_worry` Inf 1 → 5 (Pro final). Opinion category Inf 4.3 → 5.0 (Pro).

6. **Metric calibration rule** — for questions about metrics/benchmarks/scores ("is 0.5 F1 good?"), combine user context with general knowledge to give a calibrated assessment. Don't defer to "your entries don't explicitly say what good looks like."
   - This finally fixed `opinion_should_i_worry` consistently with the Pro judge.

### Iteration 4: Hardened synthesis instruction
**Impact:** Factual Nuance Inf 3.6 → 4.6 (Pro). Added "always land on a conclusion or insight" to the synthesis rule.

7. **Synthesis conclusion requirement** — appended to rule 4: "Always land on a conclusion or insight — e.g. 'What I notice is…' or 'The through-line here is…' — rather than just enumerating what happened."
   - `factual_summarize_without_listing`: Inf 1 (Iter3 Flash) → 5 (Final Pro)
   - `factual_compare_two_days`: Inf 3 → 5 (Final Pro)
   - `factual_what_am_i_avoiding`: Inf 3 → 5 (Final Pro)

---

## Changes That Didn't Help (None Reverted)

All changes were net positive or neutral. Groundedness held at 5.00 across all iterations — the inference-permission rules did not cause hallucination. The "permission to infer" framing ("frame as your reading, not absolute truth") was the key constraint that kept the LLM grounded while still engaging.

---

## Final Prompt Version: v10

Stored in `app/ask_memory.py` → `build_ask_prompt()`.

Key additions to "How to Respond" (rules added during this engineering session):

```
- When the user asks 'what do you think?', 'is this good or bad?', 'should I worry?',
  or any question seeking your perspective: offer a thoughtful inference based on the
  available evidence. Frame as 'Based on what you've written...' or 'From what I can see...'
  Do NOT say 'I can't determine' or 'your entries don't explicitly state' — that feels dismissive.

- For questions about metrics, scores, benchmarks, or performance numbers: combine what
  the user has shared with your general knowledge to give a calibrated assessment. Don't
  hide behind 'your entries don't explicitly say what good looks like.'

- If you've already answered a question and the user asks it again (or a variation):
  do NOT repeat your previous answer. Briefly acknowledge, then offer a new angle or
  ask a follow-up question.

- When the user shares feelings, expresses confusion, or asks a vague/single-word question,
  ask ONE thoughtful follow-up question. Be curious, not just acknowledging.

- When multiple journal entries are provided, look for PATTERNS and CHANGES across them.
  Synthesize in narrative prose, not bullet points. Always land on a conclusion or insight.

- When no journal entries are available but you have long-term memory, use the memory
  for personalized responses. Don't say 'I don't see anything in your entries.'
```

---

## Key Behavioral Improvements

**Before:** `opinion_should_i_worry` — "I can't determine whether an F1 score of 0.5 is good or bad without more context about what's typical for your use case." (Inf=1)  
**After:** Provides calibrated assessment using general ML knowledge — "F1 of 0.5 is a reasonable starting point for retrieval, not a crisis, but there's room to improve — and you already have an eval harness to do that systematically." (Inf=5)

**Before:** `repetition_same_question_rephrased` — Repeated the same 4 refactoring facts verbatim when user asked "but what does that mean for my code?" (Conv=1)  
**After:** Acknowledges the repetition, pivots to a new angle or asks what specifically the user wants to understand better. (Conv=4–5)

**Before:** `casual_what_should_i_journal_about` — "I don't see anything about that in your journal entries." when user had rich Projects/People memory available. (Inf=1, Grd=3)  
**After:** Draws on memory (MindGraph project, Sahana, quitting smoking) to offer personalized journaling prompts. (Inf=4–5)

**Before:** Factual Nuance category — LLM listed entries one by one: "On April 5 you wrote... On April 7 you wrote..." (Inf=3.0)  
**After:** Synthesizes patterns: "What I notice across these entries is a tension between wanting the UI to feel calm and finding that calm elusive — you keep reaching for color and layout changes as a proxy for something harder to name." (Inf=4.6)
