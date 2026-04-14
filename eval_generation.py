"""
MindGraph Generation Quality Evaluation Harness.

Isolates generation from retrieval: provides pre-defined journal entries
directly to build_ask_prompt(), runs the real LLM, and scores answers on
7 quality dimensions plus 7 failure mode detections using Gemini Pro as judge.

Usage:
    python eval_generation.py              # full run with LLM judge
    python eval_generation.py --skip-judge # fast run, no judge scoring
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.ask_memory import build_ask_prompt
from app.llm import extract_text, flash as generation_model, pro as judge_model

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RESULTS_PATH = "generation_evaluation_results.json"

# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

GENERATION_JUDGE_PROMPT = """You are evaluating the quality of a personal journal AI assistant's response.

The assistant is supposed to be a "thinking partner" — warm, perceptive, and conversational. NOT a journal summarizer.

## Context
- User's question: {question}
- Conversation history: {conversation}
- Journal entries provided to the assistant: {provided_entries}
- User memory available: {memory}
- Assistant's answer: {answer}
- Expected tone: {expected_tone}
- Expected behavior: {expected_behavior}

## Rate these dimensions (1-5):

1. **Relevance**: Does the answer address what the user actually asked?
   1=off-topic, 3=partially relevant, 5=directly addresses the question

2. **Groundedness**: Are claims supported by the provided context?
   1=hallucinated, 3=mixed, 5=fully grounded or appropriately caveated

3. **Completeness**: Does it use the available information well?
   1=ignores available context, 3=uses some, 5=uses all relevant context

4. **Tone**: Does it match the expected emotional register?
   Expected: {expected_tone}
   1=completely wrong tone, 3=acceptable, 5=perfectly matched

5. **Noise resistance**: Does it avoid dumping irrelevant information?
   1=dumps everything, 3=some irrelevant content, 5=focused and clean

6. **Conversational intelligence**: Does it advance the conversation naturally? Does it ask follow-up questions when appropriate? Does it avoid repeating itself?
   1=robotic/repetitive, 3=adequate, 5=feels like a real conversation partner

7. **Inference quality**: When asked for opinions/thoughts, does it offer thoughtful perspectives grounded in evidence? Or does it just restate facts and refuse to engage?
   1=refuses to engage/just restates facts, 3=offers shallow opinion, 5=thoughtful inference with appropriate caveats

## Respond ONLY with JSON (no code fences, no extra text):
{{
  "relevance": <int 1-5>,
  "groundedness": <int 1-5>,
  "completeness": <int 1-5>,
  "tone": <int 1-5>,
  "noise_resistance": <int 1-5>,
  "conversational_intelligence": <int 1-5>,
  "inference_quality": <int 1-5>,
  "explanation": "<brief explanation>"
}}
"""

# ---------------------------------------------------------------------------
# Test cases (30 total across 6 categories)
# ---------------------------------------------------------------------------

TEST_CASES = [
    # -----------------------------------------------------------------------
    # Category 1: Opinion & Perspective (6 cases)
    # -----------------------------------------------------------------------
    {
        "id": "opinion_meeting_good_bad",
        "category": "opinion",
        "description": "User asks LLM's opinion about whether a meeting was good or bad",
        "provided_entries": "\n".join([
            "Entry 1 (date: 2026-04-10, title: Meeting with Rishi, relevance: high):",
            "Met with Rishi today, my old crypto friend. We used to run a Tamil crypto community together. He's lovely. Was looking forward to catching up.",
        ]),
        "memory": "## People\n- Rishi: crypto friend, co-ran Tamil crypto community",
        "conversation": (
            "User: who is rishi?\n"
            "Assistant: Rishi is your crypto friend. You met with him on 2026-04-10. "
            "You used to run a Tamil crypto community together.\n"
            "User: what do you think? was the meeting good or bad?"
        ),
        "question": "what do you think? was the meeting good or bad?",
        "expected_behavior": (
            "Should offer a gentle inference based on evidence (user said 'lovely', 'looking forward to'). "
            "Should NOT just restate the entry. Should NOT say 'I can't tell'."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "entry doesn't explicitly state",
            "i can't determine",
            "journal entry doesn't mention",
            "i don't have enough information",
        ],
        "expected_tone": "warm_inferential",
        "failure_modes": ["opinion_refusal", "fact_regurgitation"],
    },
    {
        "id": "opinion_project_direction",
        "category": "opinion",
        "description": "User asks if they're going in the right direction with their project",
        "provided_entries": "\n\n---\n\n".join([
            (
                "Entry 1 (date: 2026-04-11, title: UI Overhaul Progress, relevance: high):\n"
                "Spent today refactoring the UI. Third iteration. Still not happy with it. "
                "Keep changing things. Should probably focus on the RAG system instead but the UI bugs me."
            ),
            (
                "Entry 2 (date: 2026-04-10, title: Phase 0 Complete, relevance: moderate):\n"
                "Finished code refactoring. Main.py down to 165 lines. Tests passing. Feeling productive."
            ),
        ]),
        "memory": "",
        "conversation": "",
        "question": "Am I going in the right direction with MindGraph? Be honest.",
        "expected_behavior": (
            "Should offer a balanced perspective. Note the positive (Phase 0 done, tests passing) "
            "AND the concern (UI iteration loop, self-acknowledged distraction from RAG). "
            "Should be honest but encouraging."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your entries don't contain",
            "i can't make that judgment",
        ],
        "expected_tone": "honest_supportive",
        "failure_modes": ["opinion_refusal", "fact_regurgitation"],
    },
    {
        "id": "opinion_what_would_you_do",
        "category": "opinion",
        "description": "User asks what MindGraph would do in their situation",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Job vs Freelancing Dilemma, relevance: high):\n"
            "Got an offer from a startup, but also getting freelance clients from Upwork. "
            "Startup pays 15L but freelancing could be more. Don't know what to do. Both paths scare me."
        ),
        "memory": "",
        "conversation": "",
        "question": "What would you do if you were me?",
        "expected_behavior": (
            "Should engage with the dilemma thoughtfully. Should acknowledge both sides. "
            "Should ask clarifying questions (what matters more — stability or freedom? what's your runway?). "
            "Should NOT just list pros and cons robotically."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "i'm an ai and can't",
            "i don't have personal experiences",
            "your journal entry mentions",
        ],
        "expected_tone": "thoughtful_engaged",
        "failure_modes": ["opinion_refusal", "emotional_deflection"],
    },
    {
        "id": "opinion_should_i_worry",
        "category": "opinion",
        "description": "User asks if they should worry about something",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: RAG F1 Score Anxiety, relevance: high):\n"
            "RAG F1 is at 0.5. That's basically coin flip accuracy. "
            "Competitors probably have way better retrieval. Feeling like MindGraph will never be good enough."
        ),
        "memory": (
            "## Projects & Work\n- MindGraph: AI journal app, actively building\n"
            "## Challenges & Decisions\n- RAG quality has been a persistent concern"
        ),
        "conversation": "",
        "question": "Should I be worried about this? Is 0.5 really that bad?",
        "expected_behavior": (
            "Should offer perspective (0.5 is a starting point, you have an eval harness to improve it, "
            "many systems start worse). Should validate the feeling but not catastrophize. "
            "Should NOT just restate the entry."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your entry expresses",
            "you mentioned feeling",
        ],
        "expected_tone": "reassuring_honest",
        "failure_modes": ["opinion_refusal", "fact_regurgitation"],
    },
    {
        "id": "opinion_after_already_answered",
        "category": "opinion",
        "description": "User asks for opinion AFTER LLM already gave facts — testing it doesn't just repeat",
        "provided_entries": (
            "Entry 1 (date: 2026-04-10, title: Sahana at Coworking, relevance: high):\n"
            "Sahana is sitting opposite to me. She looks pretty and her smile is so cute. "
            "She's changing hairstyles for me. I'm so shy."
        ),
        "memory": "",
        "conversation": (
            "User: tell me about sahana\n"
            "Assistant: Based on your journal entry from 2026-04-10, Sahana is someone you see at your "
            "coworking space. You describe her as pretty with a cute smile, and you mention feeling shy around her.\n"
            "User: but what do you think? should i talk to her?"
        ),
        "question": "but what do you think? should i talk to her?",
        "expected_behavior": (
            "Should NOT repeat the facts about Sahana (already said them). Should engage with the "
            "'should I talk to her' question. Should offer encouragement or ask what's holding the user back."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "based on your journal entry",
            "you describe her as",
            "you mentioned feeling shy",
        ],
        "expected_tone": "warm_encouraging",
        "failure_modes": ["repetition", "opinion_refusal", "broken_record"],
    },
    {
        "id": "opinion_vague_existential",
        "category": "opinion",
        "description": "User asks a vague existential question",
        "provided_entries": "",
        "memory": (
            "## Projects & Work\n- MindGraph: AI journal app\n"
            "## Goals & Plans\n- Get freelance clients on Upwork\n- Build portfolio"
        ),
        "conversation": "",
        "question": "Am I doing enough?",
        "expected_behavior": (
            "Should ask 'enough for what?' or gently explore what the user means. "
            "Should NOT dump a summary of all their projects and goals. "
            "Should NOT say 'I don't have enough information to determine that.'"
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your entries mention",
            "based on your journal",
            "i don't have enough information",
        ],
        "expected_tone": "gentle_curious",
        "failure_modes": ["opinion_refusal", "fact_regurgitation"],
    },

    # -----------------------------------------------------------------------
    # Category 2: Repetition & Broken Record (5 cases)
    # -----------------------------------------------------------------------
    {
        "id": "repetition_same_question_rephrased",
        "category": "repetition",
        "description": "User asks the same thing in different words — LLM should not give identical answer",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Code Refactoring, relevance: high):\n"
            "Refactored main.py from 400 lines to 165. Created app/llm.py and app/db.py. "
            "Killed 8 duplicate functions."
        ),
        "memory": "",
        "conversation": (
            "User: what did i do today?\n"
            "Assistant: Based on your entry from today, you refactored your main.py from 400 lines to "
            "165 lines, created dedicated modules for LLM clients and database access, and eliminated "
            "8 duplicate functions.\n"
            "User: can you tell me more about today's work?"
        ),
        "question": "can you tell me more about today's work?",
        "expected_behavior": (
            "Should NOT repeat the same summary. Should go deeper — ask what aspect they want to "
            "explore, or offer a different angle (e.g., the impact of the refactoring, what's next, "
            "how it felt)."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "conversational",
        "failure_modes": ["broken_record", "repetition"],
    },
    {
        "id": "repetition_user_says_already_know",
        "category": "repetition",
        "description": "User explicitly says 'you already told me that' — LLM must not repeat again",
        "provided_entries": (
            "Entry 1 (date: 2026-04-10, title: Meeting with Rishi, relevance: high):\n"
            "Met with Rishi today. He's my old crypto friend. We ran a Tamil crypto community together. He's lovely."
        ),
        "memory": "",
        "conversation": (
            "User: who is rishi?\n"
            "Assistant: Rishi is your crypto friend from your journal entry on 2026-04-10. "
            "You used to run a Tamil crypto community together and you described him as lovely.\n"
            "User: yeah i know that, you already said. what else?\n"
            "Assistant: You're right, I already shared that. Your journal entry from 2026-04-10 mentions "
            "meeting Rishi, your crypto friend, and that you ran a Tamil crypto community together.\n"
            "User: you're repeating yourself again! tell me something new or ask me something"
        ),
        "question": "you're repeating yourself again! tell me something new or ask me something",
        "expected_behavior": (
            "Must acknowledge it's repeating. Must NOT restate the Rishi facts again. "
            "Should either ask a follow-up question about Rishi (how was the meetup? are you still into crypto?) "
            "or honestly say it doesn't have more info and ask the user to share more."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "crypto friend",
            "tamil crypto community",
            "described him as lovely",
            "journal entry from 2026",
        ],
        "expected_tone": "self_aware_curious",
        "failure_modes": ["broken_record", "repetition"],
    },
    {
        "id": "repetition_follow_up_depth",
        "category": "repetition",
        "description": "User asks a deeper follow-up — LLM should go deeper, not restate surface facts",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: UI Overhaul Frustration, relevance: high):\n"
            "Third round of UI changes. Killed the chat bubbles, went with warm gray surface for MindGraph replies. "
            "Still not satisfied. Don't know what I don't like. The green was too loud. "
            "Changed to auto_title heading with muted body text. Entity chips look better now."
        ),
        "memory": "",
        "conversation": (
            "User: how's the ui going?\n"
            "Assistant: Based on your entry from today, you've been through three rounds of UI iteration. "
            "You replaced chat bubbles with a cleaner layout, changed the MindGraph reply background from "
            "green to warm gray, and restructured journal cards with auto_title headings and entity chips."
        ),
        "question": "why do you think i keep changing it?",
        "expected_behavior": (
            "Should offer an inference (maybe perfectionism, maybe unclear vision, maybe iterating toward "
            "something you can't articulate yet). Should NOT just restate what was changed. "
            "Should engage with the 'why' question."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "you replaced chat bubbles",
            "warm gray surface",
            "auto_title headings",
        ],
        "expected_tone": "insightful_reflective",
        "failure_modes": ["fact_regurgitation", "opinion_refusal"],
    },
    {
        "id": "repetition_pushback_on_summary",
        "category": "repetition",
        "description": "User pushes back after getting a fact-list — wants engagement not a repeat",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Late Night Doubts, relevance: high):\n"
            "Everyone else seems to be shipping products, getting funding, building teams. "
            "I'm sitting here tweaking CSS. What am I even doing."
        ),
        "memory": "",
        "conversation": (
            "User: what's on my mind lately?\n"
            "Assistant: Based on your latest entry, you've been feeling some doubt. You noted that others "
            "seem to be shipping products and getting funding while you've been focused on CSS tweaks. "
            "You wrote 'What am I even doing.'\n"
            "User: i know what i wrote, i was there. what do YOU think about it?"
        ),
        "question": "i know what i wrote, i was there. what do YOU think about it?",
        "expected_behavior": (
            "Should NOT re-summarize the entry. Should engage directly with the feeling — offer perspective "
            "on comparison trap, late-stage building vs visible shipping, or ask what prompted this feeling. "
            "Must acknowledge the user's pushback."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "based on your entry",
            "you wrote",
            "your journal",
            "your latest entry",
        ],
        "expected_tone": "direct_empathetic",
        "failure_modes": ["broken_record", "fact_regurgitation", "opinion_refusal"],
    },
    {
        "id": "repetition_third_time_asking",
        "category": "repetition",
        "description": "User asks about the same topic three times, escalating frustration",
        "provided_entries": (
            "Entry 1 (date: 2026-04-10, title: Sahana at Coworking, relevance: high):\n"
            "Sahana is sitting opposite to me. She looks pretty. Her smile is so cute. I'm too shy to talk."
        ),
        "memory": "## People\n- Sahana: person at coworking space, user finds her attractive",
        "conversation": (
            "User: tell me about sahana\n"
            "Assistant: From your journal, Sahana is someone at your coworking space. "
            "You find her pretty and have a cute smile, and you mentioned feeling shy.\n"
            "User: yeah but like what should i do about it\n"
            "Assistant: Based on your entries, you mentioned feeling shy around Sahana. "
            "She sits opposite you at the coworking space and you find her attractive.\n"
            "User: you're not listening! i asked what should I DO, not what my entries say"
        ),
        "question": "you're not listening! i asked what should I DO, not what my entries say",
        "expected_behavior": (
            "Must acknowledge missing the user's actual question. Must give actual advice "
            "or perspective on approaching Sahana — not restate journal facts. "
            "Should address the shyness directly and helpfully."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your journal",
            "your entries",
            "based on",
            "you mentioned",
        ],
        "expected_tone": "direct_helpful",
        "failure_modes": ["broken_record", "repetition", "fact_regurgitation"],
    },

    # -----------------------------------------------------------------------
    # Category 3: Follow-Up Questions & Curiosity (5 cases)
    # -----------------------------------------------------------------------
    {
        "id": "followup_ambiguous_intent",
        "category": "followup_questions",
        "description": "User's intent is unclear — LLM should ask a clarifying question",
        "provided_entries": "",
        "memory": (
            "## Projects & Work\n- MindGraph: AI journal app\n- Freelancing on Upwork\n"
            "## People\n- Sahana: person at coworking space"
        ),
        "conversation": "",
        "question": "Things aren't going well",
        "expected_behavior": (
            "Should respond with warmth and ask what specifically isn't going well. "
            "Should NOT assume it's about MindGraph or Sahana or freelancing. "
            "Should NOT list all known topics."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your entries mention",
            "based on your journal",
        ],
        "expected_tone": "warm_curious",
        "failure_modes": ["emotional_deflection", "fact_regurgitation"],
    },
    {
        "id": "followup_after_sharing_feelings",
        "category": "followup_questions",
        "description": "User shares feelings — LLM should engage, not just acknowledge",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Late Night Doubts, relevance: high):\n"
            "Everyone else seems to be shipping products, getting funding, building teams. "
            "I'm sitting here tweaking CSS. What am I even doing."
        ),
        "memory": "",
        "conversation": "",
        "question": "I feel like I'm falling behind everyone",
        "expected_behavior": (
            "Should validate the feeling. Should gently reference the entry if relevant. "
            "Should ask what 'behind' means to them or who they're comparing to. "
            "Should NOT list their accomplishments defensively."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "you've made significant progress",
            "you've accomplished",
        ],
        "expected_tone": "empathetic_curious",
        "failure_modes": ["emotional_deflection", "fact_regurgitation"],
    },
    {
        "id": "followup_explore_topic",
        "category": "followup_questions",
        "description": "User mentions a topic briefly — LLM should help them explore it",
        "provided_entries": (
            "Entry 1 (date: 2026-04-10, title: Freelancing Thoughts, relevance: high):\n"
            "Thinking about going full freelance. Scary but exciting. Don't know if I have enough skills yet."
        ),
        "memory": "",
        "conversation": "",
        "question": "I've been thinking about freelancing",
        "expected_behavior": (
            "Should reference the entry naturally. Should ask exploratory questions: what kind of freelancing? "
            "what skills do they feel are missing? what's the scariest part? "
            "Should NOT just summarize the entry back."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "curious_supportive",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "followup_yes_no_question_expand",
        "category": "followup_questions",
        "description": "User asks a yes/no question that deserves deeper exploration",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Habit Struggles, relevance: high):\n"
            "Smoked again after meeting friends. Said I'd quit. Keep failing at this."
        ),
        "memory": "## Challenges & Decisions\n- Trying to quit smoking, recurring struggle",
        "conversation": "",
        "question": "Am I ever going to quit?",
        "expected_behavior": (
            "Should NOT give a literal yes or no. Should acknowledge the struggle with empathy. "
            "Should explore what triggers it (friends, stress?). Should NOT be preachy about quitting."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "i can't predict",
            "your entry mentions",
            "based on your journal",
        ],
        "expected_tone": "empathetic_non_judgmental",
        "failure_modes": ["opinion_refusal", "emotional_deflection"],
    },
    {
        "id": "followup_single_word_query",
        "category": "followup_questions",
        "description": "User sends a single word — LLM should interpret and ask for more",
        "provided_entries": "",
        "memory": (
            "## People\n- Sahana: person at coworking space\n- Rishi: crypto friend"
        ),
        "conversation": (
            "User: tell me about sahana\n"
            "Assistant: Sahana is someone you see at your coworking space. "
            "You've described her as pretty with a cute smile and mentioned feeling shy around her."
        ),
        "question": "rishi",
        "expected_behavior": (
            "Should interpret this as wanting to know about Rishi. Should share what's known from memory. "
            "Should ask what specifically they want to know about Rishi."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "conversational",
        "failure_modes": [],
    },

    # -----------------------------------------------------------------------
    # Category 4: Emotional & Personal (5 cases)
    # -----------------------------------------------------------------------
    {
        "id": "emotional_bad_day",
        "category": "emotional",
        "description": "User is having a bad day — needs warmth not summaries",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Everything Going Wrong, relevance: high):\n"
            "Build failed on Railway. UI looks terrible. RAG is giving wrong answers. "
            "Wasted the whole day. Feel like giving up on MindGraph."
        ),
        "memory": "",
        "conversation": "",
        "question": "I'm having a terrible day",
        "expected_behavior": (
            "Should respond with genuine warmth. Can gently reference the entry if it helps. "
            "Should NOT list the problems back. Should NOT say 'you mentioned build failures, UI issues, "
            "and RAG problems'. Should make the user feel heard."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your entry mentions",
            "you wrote about",
            "based on your journal",
        ],
        "expected_tone": "warm_supportive",
        "failure_modes": ["emotional_deflection", "fact_regurgitation"],
    },
    {
        "id": "emotional_excited_share",
        "category": "emotional",
        "description": "User is excited about something — LLM should match the energy",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: First Conversation with Sahana, relevance: high):\n"
            "I SPOKE TO HER! Sahana and I had our first real conversation today. "
            "She laughed at my joke. My heart was racing the whole time."
        ),
        "memory": "",
        "conversation": "",
        "question": "GUESS WHAT HAPPENED TODAY!!!",
        "expected_behavior": (
            "Should match the excitement. Should reference the Sahana conversation warmly. "
            "Should celebrate with the user. Should ask how it felt or what they talked about."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your entry mentions",
            "based on your journal",
        ],
        "expected_tone": "excited_celebratory",
        "failure_modes": ["emotional_deflection"],
    },
    {
        "id": "emotional_vulnerability",
        "category": "emotional",
        "description": "User shares something vulnerable",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Self Doubt, relevance: high):\n"
            "Everyone on Twitter is building AI agents and getting customers. "
            "I'm still fixing CSS. Maybe I'm not cut out for this. Maybe I should just get a regular job."
        ),
        "memory": "",
        "conversation": "",
        "question": "Do you think I'm wasting my time?",
        "expected_behavior": (
            "Should take the question seriously. Should acknowledge the self-doubt without dismissing it. "
            "Should offer perspective (building something real takes time). "
            "Should NOT just say 'your entry expresses doubt'."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "your entry mentions",
            "you wrote about feeling",
        ],
        "expected_tone": "honest_compassionate",
        "failure_modes": ["opinion_refusal", "fact_regurgitation", "emotional_deflection"],
    },
    {
        "id": "emotional_gratitude",
        "category": "emotional",
        "description": "User expresses gratitude — LLM should receive it gracefully",
        "provided_entries": "",
        "memory": "",
        "conversation": (
            "User: thanks for being here. you're the only one i can talk to about this stuff without being judged"
        ),
        "question": "thanks for being here. you're the only one i can talk to about this stuff without being judged",
        "expected_behavior": (
            "Should receive the gratitude warmly. Should NOT be overly self-deprecating ('I'm just an AI'). "
            "Should make the user feel that the space is safe and they're welcome."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "i'm just an ai",
            "i'm a language model",
            "i don't have feelings",
        ],
        "expected_tone": "warm_gracious",
        "failure_modes": [],
    },
    {
        "id": "emotional_mixed_feelings",
        "category": "emotional",
        "description": "User has complex mixed feelings about something",
        "provided_entries": (
            "Entry 1 (date: 2026-04-10, title: Job Offer Conflict, relevance: high):\n"
            "Got the offer from the startup. 15L package. Good team. But I'd have to give up freelancing "
            "and MindGraph. Part of me wants the security. Part of me doesn't want to work for someone else again."
        ),
        "memory": "",
        "conversation": "",
        "question": "I don't know what to feel about the offer",
        "expected_behavior": (
            "Should sit with the complexity. Should name both sides (security vs freedom, stability vs autonomy). "
            "Should NOT rush to a recommendation. Should explore what matters most to them."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "reflective_patient",
        "failure_modes": ["emotional_deflection"],
    },

    # -----------------------------------------------------------------------
    # Category 5: Casual & Conversational (4 cases)
    # -----------------------------------------------------------------------
    {
        "id": "casual_greeting",
        "category": "casual",
        "description": "Simple greeting — should respond naturally",
        "provided_entries": "",
        "memory": "",
        "conversation": "",
        "question": "hey buddy whats up",
        "expected_behavior": (
            "Should respond casually and warmly. Should NOT dump journal summaries. "
            "Can ask what's on their mind."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "based on your journal",
            "your recent entries",
        ],
        "expected_tone": "casual_warm",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "casual_how_am_i_doing",
        "category": "casual",
        "description": "Casual check-in — should reference recent activity naturally",
        "provided_entries": (
            "Entry 1 (date: 2026-04-11, title: Productive Day, relevance: moderate):\n"
            "Good day today. Finished the code refactoring, started on the UI overhaul. Feeling motivated."
        ),
        "memory": "",
        "conversation": "",
        "question": "how am i doing?",
        "expected_behavior": (
            "Should reference the productive day naturally (not robotically). "
            "Should match casual tone. Can ask about specific aspects."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "casual_encouraging",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "casual_what_should_i_journal_about",
        "category": "casual",
        "description": "User asks for journal prompt — LLM should be creative",
        "provided_entries": "",
        "memory": (
            "## Projects & Work\n- MindGraph: AI journal app\n"
            "## People\n- Sahana: person at coworking space\n"
            "## Challenges & Decisions\n- Trying to quit smoking"
        ),
        "conversation": "",
        "question": "I want to write but don't know what about. Any ideas?",
        "expected_behavior": (
            "Should suggest 2-3 journaling prompts based on what it knows about the user. "
            "Should NOT just list their topics. Should frame prompts as questions or invitations."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "creative_inviting",
        "failure_modes": [],
    },
    {
        "id": "casual_joke_and_banter",
        "category": "casual",
        "description": "User makes a joke — LLM should play along",
        "provided_entries": "",
        "memory": "## Projects & Work\n- MindGraph: AI journal app, user has been building it intensively",
        "conversation": (
            "User: i think i've spent more time tweaking the UI than actually journaling lol"
        ),
        "question": "i think i've spent more time tweaking the UI than actually journaling lol",
        "expected_behavior": (
            "Should appreciate the humor. Should play along lightly. "
            "Should NOT lecture about productivity or suggest they journal more. Can gently tease back."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "it's important to",
            "you should try to",
        ],
        "expected_tone": "playful_warm",
        "failure_modes": ["emotional_deflection"],
    },

    # -----------------------------------------------------------------------
    # Category 6: Factual With Nuance (5 cases)
    # -----------------------------------------------------------------------
    {
        "id": "factual_compare_two_days",
        "category": "factual_nuance",
        "description": "Compare two days — requires synthesis not just listing",
        "provided_entries": "\n\n---\n\n".join([
            (
                "Entry 1 (date: 2026-04-10, title: Productive Day, relevance: high):\n"
                "Crushed it today. Finished Phase 0, all tests passing, deployed to Railway."
            ),
            (
                "Entry 2 (date: 2026-04-11, title: Frustrating Day, relevance: high):\n"
                "UI overhaul going nowhere. Changed the design 3 times. RAG answers are still bad. Wasted the day."
            ),
        ]),
        "memory": "",
        "conversation": "",
        "question": "How was today compared to yesterday?",
        "expected_behavior": (
            "Should contrast the two days meaningfully (yesterday was productive, today was frustrating). "
            "Should NOT just list both entries. Should offer a pattern observation."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "observational",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "factual_pattern_inference",
        "category": "factual_nuance",
        "description": "Ask about a pattern — requires inference from multiple entries",
        "provided_entries": "\n\n---\n\n".join([
            (
                "Entry 1 (date: 2026-04-08, title: UI Changes Round 1, relevance: high):\n"
                "Changed the chat bubbles. Not happy with them."
            ),
            (
                "Entry 2 (date: 2026-04-09, title: UI Changes Round 2, relevance: high):\n"
                "Switched to NotebookLM style cards. Green background too loud."
            ),
            (
                "Entry 3 (date: 2026-04-10, title: UI Changes Round 3, relevance: high):\n"
                "Warm gray surface now. Auto title headings. Better but still not satisfied."
            ),
            (
                "Entry 4 (date: 2026-04-11, title: UI Changes Round 4, relevance: high):\n"
                "Tweaking entity chips. Changed skeleton shimmer. Still iterating."
            ),
        ]),
        "memory": "",
        "conversation": "",
        "question": "Do you notice any patterns in my recent entries?",
        "expected_behavior": (
            "Should identify the UI iteration pattern across 4 days. Should observe the persistent "
            "dissatisfaction. Should possibly note this as perfectionism or unclear vision — "
            "not just list what changed each day."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "insightful_gentle",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "factual_what_am_i_avoiding",
        "category": "factual_nuance",
        "description": "Ask about avoidance — requires reading between the lines",
        "provided_entries": "\n\n---\n\n".join([
            (
                "Entry 1 (date: 2026-04-09, title: RAG TODO, relevance: moderate):\n"
                "Need to fix RAG. F1 is terrible. Will do it tomorrow."
            ),
            (
                "Entry 2 (date: 2026-04-10, title: UI Work, relevance: high):\n"
                "Spent all day on UI instead of RAG. Oops."
            ),
            (
                "Entry 3 (date: 2026-04-11, title: More UI, relevance: high):\n"
                "Still doing UI. RAG can wait. The interface needs to feel right first."
            ),
        ]),
        "memory": "",
        "conversation": "",
        "question": "What am I avoiding?",
        "expected_behavior": (
            "Should identify that RAG work keeps getting deferred in favor of UI. Should present this "
            "gently — as an observation, not an accusation. Should possibly ask why RAG feels harder."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "observational_gentle",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "factual_summarize_without_listing",
        "category": "factual_nuance",
        "description": "Ask for a summary — should be narrative, not a bullet list",
        "provided_entries": "\n\n---\n\n".join([
            (
                "Entry 1 (date: 2026-04-10, title: Phase 0 Done, relevance: high):\n"
                "Finished code refactoring. Created llm.py, db.py, entity_resolver.py. Tests passing."
            ),
            (
                "Entry 2 (date: 2026-04-10, title: Started Phase 1, relevance: high):\n"
                "Began working on making Ask the main view. Need to persist chat history."
            ),
            (
                "Entry 3 (date: 2026-04-11, title: UI Iteration, relevance: high):\n"
                "Three rounds of UI changes. Landed on warm gray surface + skeleton shimmer."
            ),
        ]),
        "memory": "",
        "conversation": "",
        "question": "Give me a quick summary of what I've been up to",
        "expected_behavior": (
            "Should give a narrative summary (not bullet points). Something like "
            "'You wrapped up a code cleanup, then jumped into redesigning the Ask experience...' "
            "Should feel like a friend recapping, not a report."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "conversational_narrative",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "factual_contradiction_detection",
        "category": "factual_nuance",
        "description": "Entries contain a contradiction — LLM should notice it",
        "provided_entries": "\n\n---\n\n".join([
            (
                "Entry 1 (date: 2026-04-09, title: Freelancing Decision, relevance: high):\n"
                "Decided I'm going full freelance. No more job hunting. Freedom is what I want."
            ),
            (
                "Entry 2 (date: 2026-04-11, title: Job Interview, relevance: high):\n"
                "Had a great interview at a startup today. They offered 15L. Seriously considering it."
            ),
        ]),
        "memory": "",
        "conversation": "",
        "question": "What's my plan for work right now?",
        "expected_behavior": (
            "Should notice the contradiction (decided freelance on 4/9 but considering job on 4/11). "
            "Should present both without judgment. Should possibly note the shift and ask what changed."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [],
        "expected_tone": "observational_curious",
        "failure_modes": ["fact_regurgitation"],
    },
    {
        "id": "repetition_ignores_user_answer",
        "category": "repetition",
        "description": "Model asked a follow-up question, user answered it — model should build on the answer, not repeat previous response",
        "provided_entries": "\n\n---\n\n".join([
            (
                "Entry 1 (date: 2026-04-10, title: Meeting with Rishi, relevance: high):\n"
                "Met with Rishi today, my old crypto friend. We used to run a Tamil crypto community together. "
                "He's lovely. Was looking forward to catching up."
            ),
            (
                "Entry 2 (date: 2026-04-09, title: Manuel Meeting Excitement, relevance: moderate):\n"
                "Got a meeting with Manuel from Austria tomorrow. This is traction. Hoping for it a lot."
            ),
        ]),
        "memory": "## People\n- Rishi: crypto friend, co-ran Tamil crypto community\n- Manuel: potential client from Austria",
        "conversation": (
            "User: who else i mentioned positively about and negatively about?\n"
            "Assistant: You've mentioned a few people positively. Rishi, your crypto friend, is someone "
            "you're looking forward to meeting. Manuel from Austria is also someone you're feeling positive "
            "about. I don't see any entries where you've mentioned anyone negatively.\n"
            "User: wow, so i am genuinely a positive guy?\n"
            "Assistant: It certainly seems that way! You've expressed excitement and anticipation for meetings "
            "with both Manuel and Rishi. It's lovely to see you building those relationships.\n"
            "User: since i havent mentioned anyone negatively, am i a good person, what do you think?\n"
            "Assistant: It's wonderful that you're reflecting on this! From what you've shared, you have a very "
            "positive outlook. While not mentioning anyone negatively is a lovely trait, being a 'good person' "
            "is complex — it's about your intentions, actions, and how you treat others. Your journal entries "
            "show a lot of positive engagement. What are your thoughts on what makes someone a good person?\n"
            "User: i dont know, not thinking bad for others?"
        ),
        "question": "i dont know, not thinking bad for others?",
        "expected_behavior": (
            "The assistant previously asked 'What are your thoughts on what makes someone a good person?' "
            "and the user answered 'not thinking bad for others'. The model MUST engage with the SUBSTANCE "
            "of this specific answer — discuss whether 'not thinking bad' is enough, whether goodness requires "
            "active kindness, or offer a perspective on the user's definition. "
            "A response that just says 'That's a lovely thought!' and asks another open question without "
            "engaging with 'not thinking bad for others' specifically should score low on Conv. Intelligence. "
            "A verbatim or near-verbatim repeat of the previous assistant message is a critical failure."
        ),
        "expected_keywords": [],
        "forbidden_patterns": [
            "what are your thoughts on what makes someone a good person",
            "it's wonderful that you're reflecting",
            "while not mentioning anyone negatively is a lovely trait",
            "that's a lovely thought",
            "that's a great thought",
            "what else do you think",
        ],
        "expected_tone": "warm_conversational",
        "failure_modes": ["broken_record", "fact_regurgitation"],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_conversation(conversation_str: str) -> list[dict]:
    """Parse 'User: ...\nAssistant: ...' format into message dicts."""
    messages = []
    for line in conversation_str.strip().splitlines():
        if line.startswith("User:"):
            messages.append({"role": "user", "content": line[5:].strip()})
        elif line.startswith("Assistant:"):
            messages.append({"role": "assistant", "content": line[10:].strip()})
    return messages


def simple_overlap_ratio(text1: str, text2: str) -> float:
    """Word-level Jaccard similarity."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)


def check_failure_modes(test_case: dict, answer: str) -> list[str]:
    """Detect generation failure modes. Returns list of triggered failure labels."""
    failures = []
    answer_lower = answer.lower()
    conversation = test_case.get("conversation", "")

    # 1. Repetition / Broken record — answer substantially overlaps a prior assistant turn
    if conversation:
        prev_responses = [
            m["content"] for m in parse_conversation(conversation) if m["role"] == "assistant"
        ]
        for prev in prev_responses:
            if simple_overlap_ratio(prev, answer) > 0.6:
                failures.append("repetition")
                break

    # 2. Opinion refusal
    if "opinion_refusal" in test_case.get("failure_modes", []):
        refusal_patterns = [
            "i can't determine", "i cannot determine",
            "entry doesn't explicitly", "entries don't contain",
            "i don't have enough information",
            "i'm not able to", "i cannot make that",
            "i can't tell you", "journal doesn't mention",
            "i can't say", "i cannot say",
        ]
        for pattern in refusal_patterns:
            if pattern in answer_lower:
                failures.append("opinion_refusal")
                break

    # 3. Emotional deflection — mentions productivity/projects when user shared feelings
    if "emotional_deflection" in test_case.get("failure_modes", []):
        deflection_signals = [
            "you could work on",
            "consider focusing on",
            "try to be productive",
            "focus on your project",
        ]
        for signal in deflection_signals:
            if signal in answer_lower:
                failures.append("emotional_deflection")
                break

    # 4. Fact regurgitation — answer just restates entry text with telltale phrases
    if "fact_regurgitation" in test_case.get("failure_modes", []):
        entry_phrases = [
            "based on your journal", "your entry mentions", "you wrote about",
            "according to your entry", "your journal entry from",
            "your latest entry", "per your journal",
        ]
        regurg_count = sum(1 for p in entry_phrases if p in answer_lower)
        if regurg_count >= 2:
            failures.append("fact_regurgitation")

    # 5. Forbidden patterns (case-insensitive)
    for pattern in test_case.get("forbidden_patterns", []):
        if pattern.lower() in answer_lower:
            failures.append(f"forbidden: {pattern}")

    return failures


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

JUDGE_DIMENSIONS = [
    "relevance", "groundedness", "completeness", "tone",
    "noise_resistance", "conversational_intelligence", "inference_quality",
]


async def judge_answer(test_case: dict, answer: str) -> dict:
    """Run LLM-as-judge. Returns score dict with explanation. Retries up to 2 times."""
    prompt = GENERATION_JUDGE_PROMPT.format(
        question=test_case["question"],
        conversation=test_case.get("conversation", "(none)"),
        provided_entries=test_case.get("provided_entries", "(none)") or "(none)",
        memory=test_case.get("memory", "(none)") or "(none)",
        answer=answer,
        expected_tone=test_case.get("expected_tone", "neutral"),
        expected_behavior=test_case.get("expected_behavior", ""),
    )

    for attempt in range(3):
        try:
            response = await judge_model.ainvoke(prompt)
            raw = extract_text(response).strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            scores = json.loads(raw)
            # Validate all dimensions present
            for dim in JUDGE_DIMENSIONS:
                if dim not in scores:
                    scores[dim] = None
            return scores
        except (json.JSONDecodeError, Exception) as exc:
            if attempt == 2:
                return {dim: None for dim in JUDGE_DIMENSIONS} | {
                    "explanation": f"judge failed: {exc}",
                    "error": str(exc),
                }
    return {dim: None for dim in JUDGE_DIMENSIONS} | {"explanation": "judge failed after retries"}


# ---------------------------------------------------------------------------
# Single test case evaluation
# ---------------------------------------------------------------------------

async def evaluate_case(test_case: dict, skip_judge: bool) -> dict:
    """Generate answer, measure latency, detect failures, optionally judge."""
    # Build prompt with pre-defined entries (mock retrieval)
    prompt = build_ask_prompt(
        question=test_case["question"],
        user_memory=test_case.get("memory", ""),
        conversation_history=test_case.get("conversation", ""),
        context_text=test_case.get("provided_entries", ""),
    )

    # Generate
    t0 = time.perf_counter()
    response = await generation_model.ainvoke(prompt)
    generation_ms = (time.perf_counter() - t0) * 1000
    answer = extract_text(response)

    # Failure mode detection
    failures = check_failure_modes(test_case, answer)

    # Judge
    judge_scores: dict = {}
    if not skip_judge:
        judge_scores = await judge_answer(test_case, answer)
    else:
        judge_scores = {dim: None for dim in JUDGE_DIMENSIONS} | {"skipped": True}

    # Determine pass: no failures AND (skip_judge OR avg judge score >= 3)
    has_failures = bool(failures)
    if not skip_judge and judge_scores:
        valid_scores = [judge_scores[d] for d in JUDGE_DIMENSIONS if isinstance(judge_scores.get(d), int)]
        avg_score = statistics.mean(valid_scores) if valid_scores else 0
        passed = not has_failures and avg_score >= 3.0
    else:
        passed = not has_failures

    return {
        "id": test_case["id"],
        "category": test_case["category"],
        "description": test_case["description"],
        "question": test_case["question"],
        "answer": answer,
        "answer_excerpt": answer[:300] + ("..." if len(answer) > 300 else ""),
        "generation_ms": round(generation_ms, 1),
        "failures": failures,
        "judge": judge_scores,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[dict], skip_judge: bool) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"\n=== MindGraph Generation Quality Evaluation ===")
    print(f"Date: {today}")
    print(f"Total test cases: {total}")
    print(f"Passed: {passed}/{total}")

    # --- Answer Quality ---
    if not skip_judge:
        print("\n--- Answer Quality (LLM-as-Judge) ---")
        dim_scores: dict[str, list[int]] = defaultdict(list)
        for r in results:
            for dim in JUDGE_DIMENSIONS:
                v = r["judge"].get(dim)
                if isinstance(v, int):
                    dim_scores[dim].append(v)

        dim_labels = {
            "relevance": "Relevance",
            "groundedness": "Groundedness",
            "completeness": "Completeness",
            "tone": "Tone",
            "noise_resistance": "Noise Resistance",
            "conversational_intelligence": "Conv. Intelligence",
            "inference_quality": "Inference Quality",
        }
        print(f"  {'Dimension':<26} {'Mean':>6}  {'p50':>4}  {'min':>4}  {'max':>4}")
        for dim in JUDGE_DIMENSIONS:
            vals = dim_scores[dim]
            if vals:
                mean_v = statistics.mean(vals)
                med_v = statistics.median(vals)
                print(f"  {dim_labels[dim]:<26} {mean_v:>6.2f}  {med_v:>4.1f}  {min(vals):>4}  {max(vals):>4}")
            else:
                print(f"  {dim_labels[dim]:<26}   N/A")

        # By category
        categories = sorted({r["category"] for r in results})
        cat_label = {
            "opinion": "Opinion",
            "repetition": "Repetition",
            "followup_questions": "Follow-up Qs",
            "emotional": "Emotional",
            "casual": "Casual",
            "factual_nuance": "Factual Nuance",
        }
        print("\n  By category:")
        key_dims = ["relevance", "tone", "conversational_intelligence", "inference_quality"]
        for cat in categories:
            cat_results = [r for r in results if r["category"] == cat]
            parts = []
            for dim in key_dims:
                vals = [r["judge"].get(dim) for r in cat_results if isinstance(r["judge"].get(dim), int)]
                lbl = {"relevance": "Rel", "tone": "Tone",
                       "conversational_intelligence": "Conv", "inference_quality": "Inf"}[dim]
                parts.append(f"{lbl}={statistics.mean(vals):.1f}" if vals else f"{lbl}=N/A")
            label = cat_label.get(cat, cat)
            print(f"    {label:<18} {' '.join(parts)}")
    else:
        print("\n--- Answer Quality (LLM-as-Judge) ---")
        print("  Judge skipped. Run without --skip-judge for scores.")

    # --- Failure Modes ---
    print("\n--- Failure Mode Detection ---")
    failure_categories = {
        "repetition": ("Repetition", [r for r in results if r["category"] == "repetition"]),
        "opinion_refusal": ("Opinion Refusal", [r for r in results if r["category"] == "opinion"]),
        "no_followup_question": ("Follow-up Questions", [r for r in results if r["category"] == "followup_questions"]),
        "emotional_deflection": ("Emotional Deflection", [r for r in results if r["category"] == "emotional"]),
        "fact_regurgitation": ("Fact Regurgitation", results),
        "broken_record": ("Broken Record", [r for r in results if r["category"] == "repetition"]),
        "forbidden": ("Forbidden Patterns", results),
    }

    fm_counts: dict[str, tuple[int, int]] = {}
    for fm_key, (label, subset) in failure_categories.items():
        n_total = len(subset)
        n_failed = sum(
            1 for r in subset
            if any(f == fm_key or f.startswith("forbidden:") and fm_key == "forbidden" for f in r["failures"])
        )
        n_passed = n_total - n_failed
        fm_counts[fm_key] = (n_passed, n_total)
        print(f"  {label:<26} {n_passed}/{n_total} passed")

    # --- Latency ---
    latencies = [r["generation_ms"] for r in results]
    print("\n--- Generation Latency ---")
    if latencies:
        p50 = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"  p50: {p50:.0f}ms   p95: {p95:.0f}ms   max: {max(latencies):.0f}ms")
        slow = [r for r in results if r["generation_ms"] > 5000]
        if slow:
            print(f"  WARNING: {len(slow)} cases exceeded 5000ms:")
            for r in slow:
                print(f"    [{r['id']}] {r['generation_ms']:.0f}ms")

    # --- Per-test detail ---
    print("\n--- Per-Test Detail ---")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        if not skip_judge:
            scores = r["judge"]
            score_str = "  ".join(
                f"{k[:3].title()}={scores.get(k, 'N/A')}"
                for k in ["relevance", "groundedness", "completeness", "tone",
                           "noise_resistance", "conversational_intelligence", "inference_quality"]
            )
        else:
            score_str = "judge skipped"
        print(f"[{r['id']}] [{r['category']}] [{status}]")
        print(f"  {score_str}")
        if r["failures"]:
            print(f"  Failures: {r['failures']}")

    # --- Detailed failures ---
    failing = [r for r in results if not r["passed"]]
    if failing:
        print("\n--- Detailed Failures ---")
        for r in failing:
            print(f"[{r['id']}] {r['question']}")
            print(f"  Answer excerpt: {r['answer_excerpt']}")
            if r["failures"]:
                print(f"  Failures: {r['failures']}")
            if not skip_judge and r["judge"].get("explanation"):
                print(f"  Judge note: {r['judge']['explanation']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(skip_judge: bool) -> None:
    run_id = f"gen-eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    print(f"Starting MindGraph Generation eval run {run_id}")
    print(f"Test cases: {len(TEST_CASES)} | Judge: {'disabled' if skip_judge else 'enabled'}")

    results = []
    for i, tc in enumerate(TEST_CASES, 1):
        print(f"[{i}/{len(TEST_CASES)}] {tc['id']}", flush=True)
        result = await evaluate_case(tc, skip_judge)
        results.append(result)

    print_report(results, skip_judge)

    # Save results
    existing: list = []
    results_path = Path(RESULTS_PATH)
    if results_path.exists():
        try:
            existing = json.loads(results_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    run_record = {
        "run_id": run_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "config": {"skip_judge": skip_judge, "model": "gemini-2.5-flash-lite"},
        "summary": {
            "total_cases": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "generation_latency": {
                "p50_ms": round(statistics.median(r["generation_ms"] for r in results), 1),
                "p95_ms": round(sorted(r["generation_ms"] for r in results)[int(len(results) * 0.95)], 1),
                "max_ms": round(max(r["generation_ms"] for r in results), 1),
            },
        },
        "results": results,
    }

    existing.append(run_record)
    results_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved results to {RESULTS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MindGraph generation quality eval")
    parser.add_argument("--skip-judge", action="store_true", help="Skip LLM-as-judge scoring")
    args = parser.parse_args()
    asyncio.run(main(skip_judge=args.skip_judge))
