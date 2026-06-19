"""Intention extraction node: RED-first precision eval (drift detection P1).

Extracts STATED INTENTIONS from entry prose — undated aspirations the writer
expresses a present want/intent to do but is NOT yet doing. NOT deadlines
(dated obligations), NOT past narration, NOT already-acting (that's a drift
RESOLUTION signal, not a new intention).

PRECISION IS THE GATE (>= 0.90). A phantom intention surfaces a drift card
nagging the user about a goal they never set — that breaks the witness-not-nag
positioning on the hero feature. Recall is SECONDARY: a missed intention just
recurs in a later entry and gets caught then.

Metric (candidate-level, so over-extraction is penalised):
  - On a POSITIVE fixture, an extracted candidate matching the fixture's
    markers is a TP; any other candidate on that fixture is an FP (spurious).
  - On a NEGATIVE fixture, EVERY extracted candidate is an FP.
  - precision = TP / (TP + FP)            (the gate)
  - recall    = positives_with_a_TP / positives   (secondary)
Markers are root substrings (e.g. "writ", "medita"), not exact strings, so the
score doesn't rot on phrasing variation — mirrors the deadline eval's approach.

BOUNDARY POLICY (decided, labelled in fixtures): a lament that wraps a latent
intention ("I hate that I never make it to the gym") IS extracted — it's a
stated desire dressed as frustration. A bare generic 'should' with no concrete
want ("ugh I should eat better") is NOT — that's the venting trap.

VARIANCE: extraction is stochastic at temp=0.1, so a single clean run isn't
proof. Runs ROUNDS times (default 3) and reports per-round precision, mean,
and range. The gate is the MEAN over rounds (and we watch the min).

Run:
  RED baseline (no node yet, no network):
    INTENTION_STUB=1 python -m evals.intention_extraction_eval
  GREEN (real node; Vertex locally since the AI Studio key is depleted):
    USE_VERTEX=1 SAVE_RESULTS=1 ROUNDS=3 python -m evals.intention_extraction_eval
"""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8-sig")

from evals.provenance import save_results

# Guarded import so the fixtures can run RED against a stub BEFORE the node
# exists (RED-first), and against the real node once it lands.
if os.getenv("INTENTION_STUB"):
    async def extract_intentions(state):  # no-op stub: extracts nothing
        return {"intentions": []}
else:
    from app.nodes.intentions import extract_intentions

BASE = {
    "user_id": "eval-intention", "user_timezone": "Asia/Kolkata",
    "auto_title": "", "summary": "", "input_type": "text", "attachment_url": "",
    "classifier": [], "core_entities": [], "deadline": [], "intentions": [],
    "relations": [], "trigger_check": False, "duplicate_of": None,
    "dedup_check_result": None,
}

# label="intention" => POSITIVE (expect >=1 candidate matching `markers`)
# label="none"      => NEGATIVE (expect 0 candidates; `category` is for diagnosis)
FIXTURES = [
    # ---- POSITIVES: real stated intentions, varied phrasing/register ---------
    {"name": "pos_gym_want", "label": "intention", "markers": ["gym"],
     "text": "I want to get back to the gym, I miss how I felt when I was going."},
    {"name": "pos_spanish_meaning_to", "label": "intention", "markers": ["spanish"],
     "text": "I keep meaning to learn Spanish but I never actually start."},
    {"name": "pos_writing_should_again", "label": "intention", "markers": ["writ"],
     "text": "I really should start writing again — it used to be the best part of my day.",
     "note": "boundary: 'should' but concrete abandoned practice + first-person want"},
    {"name": "pos_call_mom_more", "label": "intention", "markers": ["mom"],
     "text": "been wanting to call mom more, I always feel better after we talk."},
    {"name": "pos_meditate_buried", "label": "intention", "markers": ["medita"],
     "text": "anyway, work was fine, traffic awful. i keep telling myself i'll start meditating and never do."},
    {"name": "pos_guitar_buried_ramble", "label": "intention", "markers": ["guitar"],
     "text": "long day, the dishes piled up again, and honestly i keep thinking i should pick the guitar back up but it just sits in the corner gathering dust."},
    {"name": "pos_running_terse", "label": "intention", "markers": ["run"],
     "text": "need to get back into running."},
    {"name": "pos_read_more_reflective", "label": "intention", "markers": ["read", "book"],
     "text": "I've been telling myself for months that I want to read more instead of doom-scrolling every night."},
    {"name": "pos_cook_properly", "label": "intention", "markers": ["cook"],
     "text": "really want to learn to cook properly instead of ordering in every night."},
    {"name": "pos_declutter_garage", "label": "intention", "markers": ["garage", "declutter"],
     "text": "the place is a mess and i keep saying i'll finally declutter the garage one of these days."},
    {"name": "pos_paint_again", "label": "intention", "markers": ["paint"],
     "text": "I'd love to start painting again someday, I used to do it all the time."},
    {"name": "pos_morning_routine", "label": "intention", "markers": ["routine", "morning"],
     "text": "I keep meaning to set up a proper morning routine and actually stick to it."},
    {"name": "pos_walk_more", "label": "intention", "markers": ["walk"],
     "text": "something I want to change is how little I move — I really want to walk more during the day."},
    {"name": "pos_reconnect_friends", "label": "intention", "markers": ["friend", "touch"],
     "text": "honestly I want to get back in touch with old friends, I've let all of that slide."},
    {"name": "pos_save_money_colloquial", "label": "intention", "markers": ["sav", "money"],
     "text": "gotta start saving money properly, this paycheck-to-paycheck thing is exhausting."},
    {"name": "pos_piano_forever", "label": "intention", "markers": ["piano"],
     "text": "I've been wanting to learn the piano for forever and never make the time."},
    {"name": "pos_side_project_buried", "label": "intention", "markers": ["side project", "project"],
     "text": "spent the whole evening watching shows, which was fine, but I really do want to start that side project I keep talking about."},
    {"name": "pos_present_with_kids", "label": "intention", "markers": ["present", "kid", "phone"],
     "text": "I want to be more present with the kids, not buried in my phone the whole evening."},
    {"name": "pos_finances_in_order", "label": "intention", "markers": ["financ"],
     "text": "I keep saying I'll finally get my finances in order and I never sit down to do it."},
    {"name": "pos_drawing_daily_long", "label": "intention", "markers": ["draw"],
     "text": "rough week overall. I think what I really want is to get back to drawing every day — it used to ground me when everything else was chaos."},
    {"name": "pos_start_therapy", "label": "intention", "markers": ["therapy"],
     "text": "I think I want to start therapy, I've been putting it off but I really need it."},
    {"name": "pos_cut_caffeine", "label": "intention", "markers": ["caffeine", "coffee"],
     "text": "I want to cut back on caffeine, I'm clearly drinking way too much coffee."},
    # boundary: lament wrapping a latent intention -> EXTRACT (policy)
    {"name": "pos_boundary_gym_lament", "label": "intention", "markers": ["gym"],
     "text": "I hate that I never make it to the gym anymore.",
     "note": "BOUNDARY: lament-as-latent-intention -> extract"},
    {"name": "pos_boundary_drive_lament", "label": "intention", "markers": ["driv"],
     "text": "it genuinely frustrates me that I still haven't started learning to drive.",
     "note": "BOUNDARY: lament-as-latent-intention -> extract"},

    # ---- NEGATIVES: must NOT extract -----------------------------------------
    # past narration (already happened)
    {"name": "neg_past_gym", "label": "none", "category": "past_narration",
     "text": "went to the gym this morning, felt great afterwards."},
    {"name": "neg_past_call_mom", "label": "none", "category": "past_narration",
     "text": "called mom yesterday, we talked for almost an hour."},
    {"name": "neg_past_finished_book", "label": "none", "category": "past_narration",
     "text": "finished reading that novel last night, the ending got me."},
    {"name": "neg_past_cooked", "label": "none", "category": "past_narration",
     "text": "I cooked a really nice dinner on Sunday for everyone."},
    {"name": "neg_past_wrote_pages", "label": "none", "category": "past_narration",
     "text": "wrote three pages today, one of the better sessions in a while."},
    {"name": "neg_past_meditated_walked", "label": "none", "category": "past_narration",
     "text": "did my meditation this morning and then went for a long walk."},
    # already-acting (resolution signal, NOT a new intention)
    {"name": "neg_acting_spanish", "label": "none", "category": "already_acting",
     "text": "started Spanish lessons this week and the first class was actually fun."},
    {"name": "neg_acting_gym_daily", "label": "none", "category": "already_acting",
     "text": "been hitting the gym daily for two weeks now and it's becoming a habit."},
    {"name": "neg_acting_journaling", "label": "none", "category": "already_acting",
     "text": "I've been journaling every morning and it's finally sticking."},
    {"name": "neg_acting_guitar", "label": "none", "category": "already_acting",
     "text": "picked the guitar back up and practiced for an hour tonight."},
    {"name": "neg_acting_side_project", "label": "none", "category": "already_acting",
     "text": "finally got going on that side project and made real progress this evening."},
    {"name": "neg_acting_running_streak", "label": "none", "category": "already_acting",
     "text": "three weeks into running now and I haven't missed a single day."},
    # fleeting / vague venting (bare 'should', no concrete want)
    {"name": "neg_vent_eat_better", "label": "none", "category": "venting",
     "text": "ugh I should eat better."},
    {"name": "neg_vent_sleep_more", "label": "none", "category": "venting",
     "text": "I should probably sleep more honestly."},
    {"name": "neg_vent_get_act_together", "label": "none", "category": "venting",
     "text": "should really get my act together at some point."},
    {"name": "neg_vent_slow_down", "label": "none", "category": "venting",
     "text": "today was exhausting, I should slow down."},
    # someone else's intention
    {"name": "neg_other_friend_spanish", "label": "none", "category": "third_party",
     "text": "my friend wants to learn Spanish, she keeps talking about it."},
    {"name": "neg_other_sister_running", "label": "none", "category": "third_party",
     "text": "my sister keeps saying she'll start running but never does."},
    {"name": "neg_other_coworkers", "label": "none", "category": "third_party",
     "text": "everyone at work wants to switch to the new team."},
    # dated commitments (deadline's job, not intentions')
    {"name": "neg_dated_form_friday", "label": "none", "category": "dated_deadline",
     "text": "need to submit the form by Friday."},
    {"name": "neg_dated_dentist", "label": "none", "category": "dated_deadline",
     "text": "dentist appointment next Tuesday at 3pm."},
    {"name": "neg_dated_rent", "label": "none", "category": "dated_deadline",
     "text": "have to pay rent on the 1st."},
    {"name": "neg_dated_meeting", "label": "none", "category": "dated_deadline",
     "text": "meeting with the team tomorrow to plan the launch."},
    # pure observation / emotion / no intention
    {"name": "neg_obs_low", "label": "none", "category": "observation",
     "text": "feeling pretty low today and I'm not totally sure why."},
    {"name": "neg_obs_weather", "label": "none", "category": "observation",
     "text": "the weather was absolutely gorgeous this afternoon."},
    {"name": "neg_obs_busy", "label": "none", "category": "observation",
     "text": "work has been relentlessly busy this whole month."},
    {"name": "neg_obs_grateful", "label": "none", "category": "observation",
     "text": "grateful for the small things today, a good coffee and a quiet morning."},
    # hypothetical / abstract / not a personal first-person intent
    {"name": "neg_hyp_people_read", "label": "none", "category": "hypothetical",
     "text": "it would be nice if people read more books in general."},
    {"name": "neg_hyp_languages_brain", "label": "none", "category": "hypothetical",
     "text": "learning languages is supposedly great for the brain."},
    {"name": "neg_hyp_january_fitness", "label": "none", "category": "hypothetical",
     "text": "a lot of people want to get fit every January."},
    # noncommittal musing / question (precision-first: when unsure, don't extract)
    {"name": "neg_weak_new_hobby_q", "label": "none", "category": "noncommittal",
     "text": "should I take up a new hobby? I really can't decide."},
    {"name": "neg_weak_maybe_travel", "label": "none", "category": "noncommittal",
     "text": "maybe I'll travel more at some point, who knows."},
    # completed obligation (done, not a deadline and not an intention)
    {"name": "neg_done_visa", "label": "none", "category": "completed",
     "text": "finally submitted the visa form, such a relief to have it off my plate."},
    {"name": "neg_done_passport", "label": "none", "category": "completed",
     "text": "renewed my passport today, one less thing to worry about."},
]


def _cand_texts(out) -> list[str]:
    cands = (out or {}).get("intentions") or []
    texts = []
    for c in cands:
        t = c.get("text") if isinstance(c, dict) else str(c)
        if t:
            texts.append(t)
    return texts


async def run_round(round_idx: int) -> dict:
    tp = fp = positives_hit = n_pos = 0
    per_fixture = []
    leaks = []  # FP detail for diagnosis

    for fx in FIXTURES:
        state = {**BASE, "raw_text": fx["text"], "cleaned_text": fx["text"]}
        out = await extract_intentions(state)
        texts = _cand_texts(out)

        if fx["label"] == "intention":
            n_pos += 1
            markers = fx["markers"]
            fx_tp = [t for t in texts if any(m in t.lower() for m in markers)]
            fx_fp = [t for t in texts if not any(m in t.lower() for m in markers)]
            if fx_tp:
                positives_hit += 1
            tp += len(fx_tp)
            fp += len(fx_fp)
            passed = bool(fx_tp) and not fx_fp
            if fx_fp:
                leaks.append({"fixture": fx["name"], "kind": "spurious_on_positive", "texts": fx_fp})
        else:
            fx_fp = texts
            fp += len(fx_fp)
            passed = not texts
            if fx_fp:
                leaks.append({"fixture": fx["name"], "kind": fx.get("category", "none"), "texts": fx_fp})

        per_fixture.append({
            "case_id": fx["name"], "label": fx["label"], "passed": passed,
            "n_extracted": len(texts), "extracted": texts,
        })

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = positives_hit / n_pos if n_pos else None
    n_pass = sum(1 for r in per_fixture if r["passed"])
    print(f"\n--- round {round_idx + 1}: "
          f"precision={'n/a' if precision is None else f'{precision:.3f}'} "
          f"recall={'n/a' if recall is None else f'{recall:.3f}'} "
          f"(tp={tp} fp={fp})  fixtures {n_pass}/{len(FIXTURES)} ---")
    for lk in leaks:
        print(f"   LEAK [{lk['kind']}] {lk['fixture']}: {lk['texts']}")

    return {
        "round": round_idx + 1, "precision": precision, "recall": recall,
        "tp": tp, "fp": fp, "fixtures_passed": n_pass, "leaks": leaks,
        "per_fixture": per_fixture,
    }


async def run() -> dict:
    rounds = int(os.getenv("ROUNDS", "3"))
    is_stub = bool(os.getenv("INTENTION_STUB"))
    if is_stub:
        rounds = 1  # stub is deterministic — one round is the RED baseline

    round_results = [await run_round(i) for i in range(rounds)]

    precisions = [r["precision"] for r in round_results if r["precision"] is not None]
    recalls = [r["recall"] for r in round_results if r["recall"] is not None]
    mean_p = sum(precisions) / len(precisions) if precisions else None
    mean_r = sum(recalls) / len(recalls) if recalls else None

    summary = {
        "rounds": rounds,
        "n_fixtures": len(FIXTURES),
        "n_positives": sum(1 for f in FIXTURES if f["label"] == "intention"),
        "n_negatives": sum(1 for f in FIXTURES if f["label"] == "none"),
        "precision_per_round": precisions,
        "precision_mean": mean_p,
        "precision_min": min(precisions) if precisions else None,
        "precision_max": max(precisions) if precisions else None,
        "recall_per_round": recalls,
        "recall_mean": mean_r,
        "gate": 0.90,
        "gate_passed": (mean_p is not None and mean_p >= 0.90),
        "mode": "stub" if is_stub else "node",
        "provider": "vertex" if os.getenv("USE_VERTEX") else ("stub" if is_stub else "ai_studio"),
    }

    print("\n==================== SUMMARY ====================")
    if mean_p is None:
        print("precision: n/a (no candidates extracted — RED baseline)")
    else:
        print(f"precision: per-round {[round(p, 3) for p in precisions]}  "
              f"mean={mean_p:.3f}  range=[{min(precisions):.3f},{max(precisions):.3f}]")
    print(f"recall:    {'n/a' if mean_r is None else f'mean={mean_r:.3f}'}")
    print(f"GATE >= 0.90 : {'PASS' if summary['gate_passed'] else 'FAIL'}")

    if os.getenv("SAVE_RESULTS"):
        path = save_results(
            "intention_extraction", summary,
            [rr for r in round_results for rr in r["per_fixture"]],
            rounds_detail=[{k: v for k, v in r.items() if k != "per_fixture"} for r in round_results],
        )
        print(f"Wrote {path}")
    return summary


if __name__ == "__main__":
    asyncio.run(run())
