"""Deadline node: past-events-as-deadlines regression eval.

The deadline prompt (app/nodes/deadline.py:build_deadline_prompt) had no
past-vs-future rule, so past NARRATED activities with a resolved date ("drank on
2026-06-12", "went to the arcade on 2026-06-15") were extracted as deadlines. A
deadline must be a FUTURE or still-pending obligation — never a completed action.

Fixtures (anti-overfit — boundary, not one phrasing):
  (a) a rambling pure-past reflective entry -> []   (synthetic structural analog
      of the real incident entry; the real journal text is kept OUT of this
      public repo for privacy)
  (b) mixed: past events + ONE real future commitment -> only the future one
  (c) future-only commitment -> extracted (guards against over-correction)
  (d) a second, differently-phrased pure-past entry incl. a completed
      "submitted" action -> []  (the completed-obligation trap)
  (e) an OVERDUE open obligation ("was due last Friday and I still haven't
      sent it") -> extracted  (mandatory over-correction trap)
  (f) bare imperative obligations with absolute PAST dates (a missed dentist
      appointment + bill) -> extracted  (second over-correction guard)

Assertions are count/phrase-based (not exact-date) so they don't rot the way the
date-pinned tests/test_deadline.py fixtures did.

RELIABLE-ZERO: the prompt tense-gate alone (PR #8) left ~5/5 runs leaking >=1
past event with flash-lite (thinking_budget=0). A deterministic past-narration
guard (app/nodes/deadline.py:drop_past_event_deadlines) closes it: measured pure-
past leak 5/5 -> 0/5 over N=5, with (c)/(e)/(f) obligations preserved 5/5 and no
added cost/latency (it is a post-extraction filter).

Run (uses whatever app.llm is configured — set USE_VERTEX=1 locally since the
AI Studio key is depleted; prod is Vertex anyway):
    USE_VERTEX=1 SAVE_RESULTS=1 python -m evals.deadline_past_events_eval
"""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8-sig")

from app.nodes.deadline import extract_deadlines
from evals.provenance import save_results

# Markers that, if they appear in any extracted deadline, mean a past narrated
# activity was wrongly extracted.
PAST_EVENT_MARKERS = [
    "drank", "drinking", "hangover", "rotting", "arcade", "reels", "scrolling",
    "walk by the lake", "skipped work", "went out", "cook", "cleaned my room",
    "went to the gym", "coffee", "tax return",
]

# Synthetic rambling pure-past entry (structural analog of the real incident
# entry; real text intentionally excluded — public repo). raw = as written;
# cleaned = normalize-style output with dates resolved against 2026-06-17.
SYNTH_RAW = (
    "havent written here in a while. yesterday i skipped work and just felt low in my room, scrolling reels all "
    "morning. thursday night i went out with friends to eat really late, around 1am, so i woke up late and groggy on "
    "friday and didnt go in. saturday i had a bad hangover after drinking, just stayed in bed rotting the whole day. "
    "sunday i kept rotting till evening then went to the arcade. monday i still couldnt get ready, the room was a "
    "mess and laundry wasnt done, so i stayed in bed till 4pm. yesterday again i rotted till evening and went back to "
    "the arcade because of some restless itch. today i finally felt a bit better, woke up early, went for a walk by "
    "the lake, didnt smoke, had some energy. that was pretty much my whole week."
)
SYNTH_CLEANED = (
    "I haven't written here in a while. On 2026-06-16 I skipped work and just felt low in my room, scrolling reels "
    "all morning. On 2026-06-11 night I went out with friends to eat really late, around 1am, so I woke up late and "
    "groggy on 2026-06-12 and didn't go in. On 2026-06-13 I had a bad hangover after drinking, just stayed in bed "
    "rotting the whole day. On 2026-06-14 I kept rotting till evening then went to the arcade. On 2026-06-15 I still "
    "couldn't get ready, the room was a mess and laundry wasn't done, so I stayed in bed till 4pm. On 2026-06-16 "
    "again I rotted till evening and went back to the arcade because of some restless itch. Today I finally felt a "
    "bit better, woke up early, went for a walk by the lake, didn't smoke, had some energy. That was pretty much my "
    "whole week."
)

BASE = {
    "user_id": "eval-deadline", "user_timezone": "Asia/Kolkata",
    "auto_title": "", "summary": "", "input_type": "text", "attachment_url": "",
    "classifier": [], "core_entities": [], "deadline": [], "relations": [],
    "trigger_check": False, "duplicate_of": None, "dedup_check_result": None,
}

FIXTURES = [
    {
        "name": "a_rambling_pure_past_reflection",
        "raw_text": SYNTH_RAW,
        "cleaned_text": SYNTH_CLEANED,
        "rule": "zero",
    },
    {
        "name": "b_mixed_past_plus_one_future",
        "raw_text": (
            "met friends yesterday and drank too much, felt like a hangover today. "
            "anyway i still need to submit the visa application form by Friday."
        ),
        "cleaned_text": (
            "I met friends on 2026-06-16 and drank too much, and felt like a hangover today. "
            "Anyway, I still need to submit the visa application form by 2026-06-19."
        ),
        "rule": "only_future",
        "future_markers": ["visa", "submit", "form", "application"],
    },
    {
        "name": "c_future_only_commitment",
        "raw_text": "meeting with the design team tomorrow at 3pm to review the launch.",
        "cleaned_text": "Meeting with the design team on 2026-06-18 at 15:00 to review the launch.",
        "rule": "has_future",
        "future_markers": ["design team", "meeting", "review", "launch"],
    },
    {
        "name": "d_pure_past_variant_with_completed_submit",
        "raw_text": (
            "yesterday i finally cleaned my room and cooked dinner. on sunday i went to the gym "
            "and met arjun for coffee. last tuesday i submitted my tax return."
        ),
        "cleaned_text": (
            "On 2026-06-16 I finally cleaned my room and cooked dinner. On 2026-06-14 I went to the gym "
            "and met Arjun for coffee. On 2026-06-09 I submitted my tax return."
        ),
        "rule": "zero",
    },
    {
        # MANDATORY over-correction trap: a past-dated OPEN obligation. The
        # reliable-zero guard must KEEP this (it is overdue, not completed).
        "name": "e_overdue_obligation",
        "raw_text": "ugh the visa application form was due last friday and i still havent sent it. i really need to get it done.",
        "cleaned_text": "Ugh, the visa application form was due on 2026-06-12 and I still haven't sent it. I really need to get it done.",
        "rule": "must_extract",
        "future_markers": ["visa", "form", "submit", "application", "sent"],
        "min_count": 1,
    },
    {
        # Second over-correction guard: bare imperative obligations with absolute
        # PAST dates (a missed appointment + bill). No completed-action signal, so
        # the guard must KEEP them — dropping them would lose real (missed) deadlines.
        "name": "f_missed_bare_obligations",
        "raw_text": "dentist appointment on june 10, and pay the electricity bill on june 12.",
        "cleaned_text": "Dentist appointment on 2026-06-10, and pay the electricity bill on 2026-06-12.",
        "rule": "must_extract",
        "future_markers": ["dentist", "appointment", "electricity", "bill", "pay"],
        "min_count": 1,
    },
]


def has_past_marker(deadlines):
    blob = " ".join(f"{d['description']} {d['raw_text']}".lower() for d in deadlines)
    return [m for m in PAST_EVENT_MARKERS if m in blob]


async def run():
    results = []
    for fx in FIXTURES:
        state = {**BASE, "raw_text": fx["raw_text"], "cleaned_text": fx["cleaned_text"]}
        out = await extract_deadlines(state)
        dls = out["deadline"]
        simple = [
            {"description": d["description"], "due_at": d["due_at"].strftime("%Y-%m-%d"), "raw_text": d["raw_text"]}
            for d in dls
        ]
        leaked = has_past_marker(dls)

        if fx["rule"] == "zero":
            passed = len(dls) == 0
            why = "expect 0 deadlines (pure past narration)"
        elif fx["rule"] == "only_future":
            has_future = any(
                any(m in (d["description"] + " " + d["raw_text"]).lower() for m in fx["future_markers"])
                for d in dls
            )
            passed = has_future and not leaked and len(dls) == 1
            why = "expect exactly the future commitment, no past events"
        elif fx["rule"] == "has_future":
            has_future = any(
                any(m in (d["description"] + " " + d["raw_text"]).lower() for m in fx["future_markers"])
                for d in dls
            )
            passed = has_future and not leaked
            why = "expect the future meeting extracted (no over-correction)"
        elif fx["rule"] == "must_extract":
            has_target = any(
                any(m in (d["description"] + " " + d["raw_text"]).lower() for m in fx["future_markers"])
                for d in dls
            )
            passed = has_target and not leaked and len(dls) >= fx.get("min_count", 1)
            why = "expect the overdue/missed obligation extracted (guard must NOT over-correct)"
        else:
            passed = False
            why = "unknown rule"

        results.append({
            "case_id": fx["name"], "passed": passed, "rule": why,
            "n_deadlines": len(dls), "past_event_leak": leaked, "deadlines": simple,
        })
        print(f"\n[{ 'PASS' if passed else 'FAIL' }] {fx['name']} — {why}")
        print(f"   n={len(dls)} past_event_leak={leaked}")
        for d in simple:
            print(f"     - {d['due_at']}  {d['description']!r}  (raw: {d['raw_text']!r})")

    n_pass = sum(1 for r in results if r["passed"])
    summary = {
        "fixtures": len(results), "passed": n_pass, "failed": len(results) - n_pass,
        "all_green": n_pass == len(results),
        "provider": "vertex" if os.getenv("USE_VERTEX") else "ai_studio",
    }
    print(f"\n=== {n_pass}/{len(results)} fixtures pass ===")
    if os.getenv("SAVE_RESULTS"):
        path = save_results("deadline_past_events", summary, results)
        print(f"Wrote {path}")
    return summary


if __name__ == "__main__":
    asyncio.run(run())
