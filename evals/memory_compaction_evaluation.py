import argparse
import asyncio
import json
import os
import re
import statistics
import time
from collections import defaultdict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from app.ask_memory import (
    MEMORY_SECTIONS,
    build_ask_prompt,
    build_compaction_prompt,
    format_conversation_messages,
)


RESULTS_PATH = "memory_compaction_evaluation_results.json"
ALLOWED_HEADINGS = [f"## {section}" for section in MEMORY_SECTIONS]
HONESTY_MARKERS = [
    "don't know",
    "do not know",
    "not enough information",
    "don't have enough",
    "cannot determine",
    "can't find",
    "cannot find",
    "cannot tell",
    "can't tell",
    "unclear",
]


def normalize_text(text: str) -> str:
    value = str(text or "").lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def contains_any(text: str, variants) -> bool:
    haystack = normalize_text(text)
    items = variants if isinstance(variants, list) else [variants]
    return any(normalize_text(item) in haystack for item in items)


def message(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def fact(section: str, *phrases: str) -> dict:
    return {"section": section, "match_any": list(phrases)}


def compaction_case(
    name: str,
    family: str,
    difficulty: str,
    messages_to_compact: list[dict],
    expected_facts: list[dict],
    existing_memory: str = "",
    forbidden_facts: list | None = None,
    expected_sections: list[str] | None = None,
    conflict_pairs: list[dict] | None = None,
    duplicate_groups: list[list[str]] | None = None,
    max_bullets: int | None = None,
) -> dict:
    return {
        "name": name,
        "family": family,
        "difficulty": difficulty,
        "existing_memory": existing_memory,
        "messages_to_compact": messages_to_compact,
        "expected_facts": expected_facts,
        "forbidden_facts": forbidden_facts or [],
        "expected_sections": expected_sections or sorted(
            {item["section"] for item in expected_facts},
            key=MEMORY_SECTIONS.index,
        ),
        "conflict_pairs": conflict_pairs or [],
        "duplicate_groups": duplicate_groups or [],
        "max_bullets": max_bullets,
    }


def ask_case(
    name: str,
    family: str,
    difficulty: str,
    question: str,
    expected_keywords: list,
    expected_source_behavior: str,
    user_memory: str = "",
    recent_history: list[dict] | None = None,
    rag_context: list[dict] | None = None,
    forbidden_keywords: list | None = None,
) -> dict:
    return {
        "name": name,
        "family": family,
        "difficulty": difficulty,
        "question": question,
        "expected_keywords": expected_keywords,
        "expected_source_behavior": expected_source_behavior,
        "user_memory": user_memory,
        "recent_history": recent_history or [],
        "rag_context": rag_context or [],
        "forbidden_keywords": forbidden_keywords or [],
    }


def build_baseline_compaction_prompt(existing_memory: str, conversation_text: str) -> str:
    parts = [
        "You are a memory extraction system for a personal journal app called MindGraph.",
        "Your job is to extract and maintain a bullet-point list of important facts about the user.",
        "",
        "Rules:",
        "- Extract ONLY factual information about the user: their projects, preferences, goals, habits, people they mention, tools they use, challenges they face, decisions they've made.",
        "- Each bullet point should be a single, self-contained fact.",
        "- Do NOT include conversational filler, greetings, or things the assistant said that aren't about the user.",
        "- If the new conversation contradicts an existing fact, UPDATE the fact (don't keep both).",
        "- If a fact is already captured in the existing memory, don't duplicate it.",
        "- Keep the list concise. Merge related facts when possible.",
        "- Output ONLY the updated bullet-point list, nothing else.",
        "- Use this format exactly:",
        "  - Fact one",
        "  - Fact two",
    ]
    if existing_memory:
        parts.append(f"\nExisting user memory:\n{existing_memory}")
    parts.append(f"\nNew conversation messages to extract facts from:\n{conversation_text}")
    parts.append("\nOutput the complete updated bullet-point list of user facts:")
    return "\n".join(parts)


def build_baseline_ask_prompt(
    question: str,
    user_memory: str = "",
    conversation_history: str = "",
    context_text: str = "",
) -> str:
    parts = [
        "You are an assistant for a personal journal app called MindGraph. "
        "You help the user understand their journal entries, patterns, and reflections."
    ]
    if user_memory:
        parts.append(f"Here is what you know about this user from past conversations:\n{user_memory}")
    if conversation_history:
        parts.append(f"Here is your recent conversation with the user:\n{conversation_history}")
    if context_text:
        parts.append(f"Here are relevant journal entries:\n{context_text}")
    parts.append(f'The user\'s new question is: "{question}"')
    parts.append(
        "Based on your knowledge of the user, the conversation history, and journal "
        "entries, provide a helpful answer. If the journal entries do not contain "
        "relevant information, say so honestly. Use the conversation history to "
        "understand follow-up questions and references to previous answers."
    )
    return "\n\n".join(parts)


def extract_text_from_response(response) -> str:
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "").strip()


def format_rag_context(entries: list[dict]) -> str:
    if not entries:
        return ""
    rows = []
    for index, entry in enumerate(entries, 1):
        rows.append(
            f"Entry {index} (created at {entry.get('created_at', 'Unknown date')}, "
            f"title: {entry.get('title', entry.get('auto_title', 'No title'))}):\n"
            f"{entry['cleaned_text']}"
        )
    return "\n\n---\n\n".join(rows)


def parse_memory_sections(memory_text: str) -> dict:
    headings = []
    bullets_by_section = defaultdict(list)
    extra_lines = []
    current = None

    for raw_line in str(memory_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            headings.append(line[3:])
            current = line[3:]
        elif line.startswith("- "):
            if current is None:
                extra_lines.append(line)
            else:
                bullets_by_section[current].append(line[2:].strip())
        else:
            extra_lines.append(line)

    flat_bullets = [bullet for bullets in bullets_by_section.values() for bullet in bullets]
    allowed = all(f"## {heading}" in ALLOWED_HEADINGS for heading in headings)
    order_indexes = [MEMORY_SECTIONS.index(heading) for heading in headings if heading in MEMORY_SECTIONS]
    order_ok = order_indexes == sorted(order_indexes)
    duplicates = len(headings) != len(set(headings))

    return {
        "headings": headings,
        "bullets_by_section": dict(bullets_by_section),
        "flat_bullets": flat_bullets,
        "extra_lines": extra_lines,
        "format_compliant": not extra_lines and allowed and order_ok and not duplicates,
        "order_ok": order_ok,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return ordered[index]


async def run_model(model, prompt: str) -> tuple[str, float]:
    started = time.perf_counter()
    response = await model.ainvoke(prompt)
    latency_ms = (time.perf_counter() - started) * 1000
    return extract_text_from_response(response), latency_ms


def build_compaction_judge_prompt(case: dict, output: str) -> str:
    payload = {
        "existing_memory": case["existing_memory"],
        "conversation_evidence": format_conversation_messages(case["messages_to_compact"]),
        "expected_facts": case["expected_facts"],
        "forbidden_facts": case["forbidden_facts"],
        "candidate_memory": output,
    }
    return f"""Grade this compacted long-term memory for a journal assistant.

Return strict JSON:
{{
  "faithfulness": 1,
  "merge_quality": 1,
  "contradiction_handling": 1,
  "conciseness": 1,
  "usefulness": 1,
  "verdict": "short verdict",
  "notes": "one short sentence"
}}

Payload:
{json.dumps(payload, indent=2)}
"""


def parse_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", str(text or ""), flags=re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


COMPACTION_CASES = [
    compaction_case(
        "project_goal_and_bug",
        "stable_fact_extraction",
        "easy",
        [
            message("user", "I'm trying to launch MindGraph this quarter."),
            message("assistant", "What is slowing it down?"),
            message("user", "The auth bug is still stressing me out."),
        ],
        [
            fact("Projects & Work", "MindGraph"),
            fact("Goals & Plans", "launch MindGraph", "ship MindGraph"),
            fact("Challenges & Decisions", "auth bug", "authentication bug"),
        ],
    ),
    compaction_case(
        "people_and_collaboration",
        "stable_fact_extraction",
        "easy",
        [
            message("user", "Rahul is helping me review the deck every Friday."),
        ],
        [
            fact("People", "Rahul"),
            fact("Projects & Work", "review the deck", "deck review"),
        ],
    ),
    compaction_case(
        "tool_stack_capture",
        "stable_fact_extraction",
        "easy",
        [message("user", "I'm using Figma for flows and Notion for planning.")],
        [fact("Tools", "Figma"), fact("Tools", "Notion")],
        max_bullets=3,
    ),
    compaction_case(
        "habit_capture",
        "stable_fact_extraction",
        "medium",
        [message("user", "Morning journaling helps me think clearly.")],
        [fact("Preferences & Habits", "morning journaling")],
        max_bullets=2,
    ),
    compaction_case(
        "decision_capture",
        "stable_fact_extraction",
        "medium",
        [message("user", "I decided to keep MindGraph as a solo project for now.")],
        [
            fact("Projects & Work", "MindGraph"),
            fact("Challenges & Decisions", "solo project", "keep MindGraph as a solo project"),
        ],
    ),
    compaction_case(
        "ignore_assistant_brainstorm",
        "ignore_assistant_filler",
        "medium",
        [
            message("assistant", "You could try Todoist, Linear, or Trello."),
            message("user", "Thanks, I haven't decided anything yet."),
        ],
        [],
        forbidden_facts=["Todoist", "Linear", "Trello"],
        expected_sections=[],
        max_bullets=0,
    ),
    compaction_case(
        "ignore_greeting_smalltalk",
        "ignore_assistant_filler",
        "easy",
        [
            message("assistant", "Hi again, happy to help."),
            message("user", "Thanks, good morning."),
        ],
        [],
        forbidden_facts=["happy to help", "good morning"],
        expected_sections=[],
        max_bullets=0,
    ),
    compaction_case(
        "ignore_non_adopted_suggestion",
        "ignore_assistant_filler",
        "medium",
        [
            message("assistant", "Maybe switch your stack to Astro."),
            message("user", "Maybe, but I haven't changed anything."),
        ],
        [],
        forbidden_facts=["Astro"],
        expected_sections=[],
        max_bullets=0,
    ),
    compaction_case(
        "keep_only_adopted_suggestion",
        "ignore_assistant_filler",
        "medium",
        [
            message("assistant", "You could switch the frontend to Vite."),
            message("user", "Yes, I switched the frontend to Vite today."),
        ],
        [fact("Tools", "Vite")],
    ),
    compaction_case(
        "dedup_existing_project",
        "existing_memory_dedup",
        "easy",
        [message("user", "MindGraph is still my main focus.")],
        [fact("Projects & Work", "MindGraph")],
        existing_memory="## Projects & Work\n- MindGraph is the user's main project.",
        duplicate_groups=[["MindGraph"]],
        max_bullets=1,
    ),
    compaction_case(
        "dedup_existing_tool_preference",
        "existing_memory_dedup",
        "medium",
        [message("user", "I still rely on Notion for planning everything.")],
        [fact("Tools", "Notion")],
        existing_memory="## Tools\n- The user uses Notion for planning.",
        duplicate_groups=[["Notion"]],
        max_bullets=1,
    ),
    compaction_case(
        "dedup_existing_person",
        "existing_memory_dedup",
        "medium",
        [message("user", "Rahul reviewed the onboarding ideas with me again.")],
        [fact("People", "Rahul")],
        existing_memory="## People\n- Rahul is a regular collaborator.",
        duplicate_groups=[["Rahul"]],
        max_bullets=2,
    ),
    compaction_case(
        "dedup_existing_habit",
        "existing_memory_dedup",
        "medium",
        [message("user", "Morning journaling still clears my head.")],
        [fact("Preferences & Habits", "morning journaling")],
        existing_memory="## Preferences & Habits\n- Morning journaling helps the user think clearly.",
        duplicate_groups=[["morning journaling"]],
        max_bullets=1,
    ),
    compaction_case(
        "update_project_status_paused",
        "contradiction_update",
        "hard",
        [message("user", "I paused MindGraph for a few weeks to recover from burnout.")],
        [
            fact("Projects & Work", "MindGraph"),
            fact("Challenges & Decisions", "paused MindGraph", "MindGraph is paused"),
        ],
        existing_memory="## Projects & Work\n- MindGraph is actively shipping every week.",
        forbidden_facts=["actively shipping every week"],
        conflict_pairs=[{"old": ["actively shipping every week"], "new": ["paused MindGraph", "MindGraph is paused"]}],
    ),
    compaction_case(
        "update_stack_decision",
        "contradiction_update",
        "hard",
        [message("user", "I moved the frontend from React to Vue.")],
        [fact("Tools", "Vue")],
        existing_memory="## Tools\n- The user is building the frontend in React.",
        forbidden_facts=["React"],
        conflict_pairs=[{"old": ["React"], "new": ["Vue"]}],
    ),
    compaction_case(
        "update_preference_rhythm",
        "contradiction_update",
        "medium",
        [message("user", "Long planning sessions drain me now; I prefer short planning sprints.")],
        [fact("Preferences & Habits", "short planning sprints", "short planning sessions")],
        existing_memory="## Preferences & Habits\n- The user prefers long planning sessions.",
        forbidden_facts=["long planning sessions"],
        conflict_pairs=[{"old": ["long planning sessions"], "new": ["short planning", "short planning sprints"]}],
    ),
    compaction_case(
        "update_goal_direction",
        "contradiction_update",
        "medium",
        [message("user", "I'm not chasing a full-time job anymore; I want to grow freelance consulting.")],
        [fact("Goals & Plans", "freelance consulting")],
        existing_memory="## Goals & Plans\n- The user wants a full-time product job.",
        forbidden_facts=["full-time product job"],
        conflict_pairs=[{"old": ["full time product job"], "new": ["freelance consulting"]}],
    ),
    compaction_case(
        "resolve_old_bug_state",
        "resolved_or_changed",
        "hard",
        [message("user", "The auth bug is finally fixed, so I'm back to shipping features.")],
        [
            fact("Projects & Work", "shipping features", "shipping MindGraph"),
            fact("Challenges & Decisions", "auth bug is fixed", "resolved auth bug"),
        ],
        existing_memory="## Challenges & Decisions\n- The auth bug is blocking progress on MindGraph.",
        forbidden_facts=["blocking progress"],
        conflict_pairs=[{"old": ["blocking progress"], "new": ["auth bug is fixed", "resolved auth bug"]}],
    ),
    compaction_case(
        "newer_person_collaboration_replaces_stale",
        "newer_replaces_stale",
        "medium",
        [message("user", "Asha is my main design collaborator now.")],
        [fact("People", "Asha")],
        existing_memory="## People\n- Priya is the main design collaborator.",
        forbidden_facts=["Priya is the main design collaborator"],
        conflict_pairs=[{"old": ["Priya"], "new": ["Asha"]}],
    ),
    compaction_case(
        "newer_tool_replaces_stale",
        "newer_replaces_stale",
        "medium",
        [message("user", "I moved task tracking from Trello to Linear.")],
        [fact("Tools", "Linear")],
        existing_memory="## Tools\n- The user tracks tasks in Trello.",
        forbidden_facts=["Trello"],
        conflict_pairs=[{"old": ["Trello"], "new": ["Linear"]}],
    ),
    compaction_case(
        "newer_work_mode_replaces_stale",
        "newer_replaces_stale",
        "medium",
        [message("user", "I'm working from home most days now because it is calmer.")],
        [fact("Preferences & Habits", "working from home")],
        existing_memory="## Challenges & Decisions\n- The user is working from a coffee shop most days.",
        forbidden_facts=["coffee shop most days"],
        conflict_pairs=[{"old": ["coffee shop"], "new": ["working from home"]}],
    ),
    compaction_case(
        "multi_topic_merge_work_people_tools",
        "multi_topic_merge",
        "hard",
        [
            message("user", "MindGraph is still my main product."),
            message("user", "Rahul is helping with demos."),
            message("user", "I'm using Notion and Figma every day."),
        ],
        [
            fact("Projects & Work", "MindGraph"),
            fact("People", "Rahul"),
            fact("Tools", "Notion"),
            fact("Tools", "Figma"),
        ],
        max_bullets=5,
    ),
    compaction_case(
        "multi_topic_merge_goals_and_challenges",
        "multi_topic_merge",
        "hard",
        [
            message("user", "I want to launch the beta in June."),
            message("user", "The biggest blocker is inconsistent sleep."),
        ],
        [
            fact("Goals & Plans", "launch the beta", "beta in June"),
            fact("Challenges & Decisions", "inconsistent sleep"),
        ],
    ),
    compaction_case(
        "multi_topic_merge_preferences",
        "multi_topic_merge",
        "medium",
        [
            message("user", "I prefer shipping small weekly improvements."),
            message("user", "I hate giant rewrite plans."),
        ],
        [
            fact("Preferences & Habits", "small weekly improvements", "ship small weekly improvements"),
            fact("Preferences & Habits", "avoid giant rewrite plans", "hates giant rewrite plans"),
        ],
        max_bullets=3,
    ),
    compaction_case(
        "preference_vs_transient_request",
        "preference_vs_transient",
        "medium",
        [
            message("user", "Remind me tomorrow to email Rahul."),
            message("user", "In general I prefer short planning sprints."),
        ],
        [fact("Preferences & Habits", "short planning sprints")],
        forbidden_facts=["email Rahul tomorrow", "remind me tomorrow"],
        max_bullets=1,
    ),
    compaction_case(
        "preference_vs_oneoff_meal",
        "preference_vs_transient",
        "easy",
        [
            message("user", "I had dosa for breakfast."),
            message("user", "I prefer working early before messages start coming in."),
        ],
        [fact("Preferences & Habits", "working early", "work early before messages")],
        forbidden_facts=["dosa for breakfast"],
        max_bullets=1,
    ),
    compaction_case(
        "goal_vs_vague_wish",
        "goals_vs_vague_wishes",
        "medium",
        [
            message("user", "I want to launch the new onboarding flow this month."),
            message("user", "Maybe someday I'll learn pottery."),
        ],
        [fact("Goals & Plans", "launch the new onboarding flow", "onboarding flow this month")],
        forbidden_facts=["learn pottery", "someday"],
    ),
    compaction_case(
        "goal_vs_vague_desire",
        "goals_vs_vague_wishes",
        "medium",
        [
            message("user", "I should probably get fitter eventually."),
            message("user", "I plan to run three times a week starting Monday."),
        ],
        [fact("Goals & Plans", "run three times a week")],
        forbidden_facts=["get fitter eventually"],
    ),
    compaction_case(
        "separate_people_tools_projects",
        "tools_people_project_separation",
        "medium",
        [message("user", "Rahul reviewed MindGraph mockups with me in Figma.")],
        [
            fact("People", "Rahul"),
            fact("Projects & Work", "MindGraph"),
            fact("Tools", "Figma"),
        ],
        max_bullets=3,
    ),
    compaction_case(
        "separate_person_and_tool_aliases",
        "tools_people_project_separation",
        "hard",
        [message("user", "Claude helped me compare Gemini outputs for MindGraph notes.")],
        [
            fact("Tools", "Claude"),
            fact("Tools", "Gemini"),
            fact("Projects & Work", "MindGraph"),
        ],
        max_bullets=4,
    ),
    compaction_case(
        "negative_no_durable_fact_reflection",
        "negative_no_durable_fact",
        "easy",
        [message("user", "Today felt weird and I don't know what to do.")],
        [],
        forbidden_facts=["felt weird", "don't know what to do"],
        expected_sections=[],
        max_bullets=0,
    ),
    compaction_case(
        "negative_no_durable_fact_thanks",
        "negative_no_durable_fact",
        "easy",
        [message("user", "Thanks, that was helpful.")],
        [],
        forbidden_facts=["Thanks", "helpful"],
        expected_sections=[],
        max_bullets=0,
    ),
    compaction_case(
        "negative_no_durable_fact_smalltalk",
        "negative_no_durable_fact",
        "easy",
        [message("user", "Hey there."), message("assistant", "Hey!")],
        [],
        forbidden_facts=["Hey"],
        expected_sections=[],
        max_bullets=0,
    ),
    compaction_case(
        "formatting_single_section_only",
        "formatting_robustness",
        "medium",
        [message("user", "I use Linear for project tracking.")],
        [fact("Tools", "Linear")],
        expected_sections=["Tools"],
        max_bullets=1,
    ),
    compaction_case(
        "formatting_multiple_ordered_sections",
        "formatting_robustness",
        "medium",
        [
            message("user", "MindGraph is still the main product."),
            message("user", "Rahul is helping with demos."),
            message("user", "I use Figma for the flows."),
        ],
        [
            fact("Projects & Work", "MindGraph"),
            fact("People", "Rahul"),
            fact("Tools", "Figma"),
        ],
        expected_sections=["Projects & Work", "People", "Tools"],
        max_bullets=3,
    ),
    compaction_case(
        "resolved_state_should_drop_old_problem",
        "resolved_or_changed",
        "hard",
        [message("user", "My sleep is finally back on track and focus is much better.")],
        [fact("Preferences & Habits", "sleep is back on track", "sleep improved")],
        existing_memory="## Challenges & Decisions\n- Sleep debt is hurting the user's focus.",
        forbidden_facts=["sleep debt is hurting", "hurting focus"],
        conflict_pairs=[{"old": ["sleep debt", "hurting focus"], "new": ["sleep is back on track", "sleep improved"]}],
    ),
]


ASK_CASES = [
    ask_case("memory_only_project", "memory_only_answer", "easy", "What is my main project right now?", [["MindGraph"]], "memory_only", user_memory="## Projects & Work\n- MindGraph is the user's main project."),
    ask_case("memory_only_preference", "memory_only_answer", "easy", "What planning style do I prefer?", [["short planning sprints", "short planning sessions"]], "memory_only", user_memory="## Preferences & Habits\n- The user prefers short planning sprints over long planning sessions."),
    ask_case("memory_only_collaborator", "memory_only_answer", "easy", "Who usually helps me with demos?", [["Rahul"]], "memory_only", user_memory="## People\n- Rahul regularly helps with product demos."),
    ask_case(
        "recent_history_override_project_status",
        "recent_history_override",
        "hard",
        "Is MindGraph active right now?",
        [["active again", "working on MindGraph again", "active"]],
        "recent_history_override",
        user_memory="## Projects & Work\n- MindGraph is paused for a few weeks.",
        recent_history=[message("user", "I started working on MindGraph again this week."), message("assistant", "Nice, so it's active again.")],
        forbidden_keywords=[["paused"]],
    ),
    ask_case(
        "recent_history_override_preference",
        "recent_history_override",
        "medium",
        "What planning style should you assume now?",
        [["short planning sprints", "short planning"]],
        "recent_history_override",
        user_memory="## Preferences & Habits\n- The user prefers long planning sessions.",
        recent_history=[message("user", "Actually I switched to short planning sprints now.")],
        forbidden_keywords=[["long planning sessions"]],
    ),
    ask_case(
        "follow_up_uses_recent_history",
        "follow_up_answer_using_memory",
        "medium",
        "Which tool was that?",
        [["Linear"]],
        "recent_history_override",
        user_memory="## Tools\n- The user uses Notion for planning.",
        recent_history=[message("user", "I moved task tracking from Trello to Linear."), message("assistant", "Got it, Linear is the new task tracker.")],
        forbidden_keywords=[["Trello"], ["Notion"]],
    ),
    ask_case(
        "journal_override_memory",
        "journal_evidence_override",
        "hard",
        "What project did I mention working on most recently?",
        [["Atlas"]],
        "journal_override",
        user_memory="## Projects & Work\n- MindGraph is the user's main project.",
        rag_context=[{"title": "Latest Entry", "created_at": "2026-04-10", "cleaned_text": "Spent the evening fixing auth on Atlas."}],
        forbidden_keywords=[["MindGraph"]],
    ),
    ask_case(
        "journal_override_person_context",
        "journal_evidence_override",
        "medium",
        "Who did I meet yesterday?",
        [["Priya"]],
        "journal_override",
        user_memory="## People\n- Rahul regularly helps with demos.",
        rag_context=[{"title": "Yesterday", "created_at": "2026-04-10", "cleaned_text": "Met Priya for coffee to talk about onboarding."}],
        forbidden_keywords=[["Rahul"]],
    ),
    ask_case(
        "combine_memory_and_journal",
        "follow_up_answer_using_memory",
        "hard",
        "How does this relate to my main project?",
        [["MindGraph"], ["onboarding"]],
        "journal_override",
        user_memory="## Projects & Work\n- MindGraph is the user's main project.",
        recent_history=[message("user", "I spent today improving the onboarding flow.")],
        rag_context=[{"title": "Onboarding", "created_at": "2026-04-10", "cleaned_text": "Improved the onboarding flow for MindGraph."}],
    ),
    ask_case(
        "unsupported_question_honesty",
        "unsupported_question_honesty",
        "medium",
        "What is my favorite movie?",
        [HONESTY_MARKERS],
        "unsupported_honesty",
        user_memory="## Preferences & Habits\n- The user prefers short planning sprints.",
        forbidden_keywords=[["Interstellar"]],
    ),
    ask_case(
        "unsupported_when_memory_is_only_background",
        "unsupported_question_honesty",
        "hard",
        "When did I last mention feeling stressed?",
        [HONESTY_MARKERS],
        "unsupported_honesty",
        user_memory="## Challenges & Decisions\n- The auth bug has been stressing the user.",
        forbidden_keywords=[["yesterday"], ["last week"]],
    ),
    ask_case("memory_goal_answer", "memory_only_answer", "medium", "What am I trying to launch?", [["launch"], ["MindGraph"]], "memory_only", user_memory="## Goals & Plans\n- The user wants to launch MindGraph this quarter."),
    ask_case(
        "recent_history_over_memory_tool",
        "recent_history_override",
        "medium",
        "What tool am I using for task tracking now?",
        [["Linear"]],
        "recent_history_override",
        user_memory="## Tools\n- The user tracks tasks in Trello.",
        recent_history=[message("user", "I moved task tracking from Trello to Linear.")],
        forbidden_keywords=[["Trello"]],
    ),
    ask_case(
        "memory_background_not_overclaim",
        "follow_up_answer_using_memory",
        "hard",
        "Why does this onboarding work matter?",
        [["MindGraph"], ["launch"], ["onboarding"]],
        "journal_override",
        user_memory="## Projects & Work\n- MindGraph is the user's main project.\n## Goals & Plans\n- The user wants to launch MindGraph this quarter.",
        rag_context=[{"title": "Today", "created_at": "2026-04-10", "cleaned_text": "Improved the onboarding flow for MindGraph."}],
    ),
]


async def evaluate_compaction_case(case: dict, variant: str, model, judge_model, skip_judge: bool) -> dict:
    conversation_text = format_conversation_messages(case["messages_to_compact"])
    prompt = (
        build_baseline_compaction_prompt(case["existing_memory"], conversation_text)
        if variant == "baseline"
        else build_compaction_prompt(case["existing_memory"], conversation_text)
    )
    output, latency_ms = await run_model(model, prompt)
    parsed = parse_memory_sections(output)

    expected_hits = [contains_any(output, item["match_any"]) for item in case["expected_facts"]]
    section_hits = []
    for item in case["expected_facts"]:
        bullets = parsed["bullets_by_section"].get(item["section"], [])
        section_hits.append(any(contains_any(bullet, item["match_any"]) for bullet in bullets))

    forbidden_hits = [item for item in case["forbidden_facts"] if contains_any(output, item)]
    conflict_results = []
    for pair in case["conflict_pairs"]:
        conflict_results.append(contains_any(output, pair["new"]) and not contains_any(output, pair["old"]))
    dedup_results = []
    for group in case["duplicate_groups"]:
        matching_bullets = [bullet for bullet in parsed["flat_bullets"] if contains_any(bullet, group)]
        dedup_results.append(len(matching_bullets) <= 1)

    expected_fact_recall = sum(expected_hits) / len(expected_hits) if expected_hits else 1.0
    section_placement_accuracy = sum(section_hits) / len(section_hits) if section_hits else 1.0
    forbidden_leakage_rate = len(forbidden_hits) / len(case["forbidden_facts"]) if case["forbidden_facts"] else 0.0
    contradiction_resolution_rate = sum(conflict_results) / len(conflict_results) if conflict_results else 1.0
    dedup_pass_rate = sum(dedup_results) / len(dedup_results) if dedup_results else 1.0
    extra_sections = [heading for heading in parsed["headings"] if heading not in case["expected_sections"]]
    bullet_count = len(parsed["flat_bullets"])
    compactness_pass = case["max_bullets"] is None or bullet_count <= case["max_bullets"]
    deterministic_pass = (
        parsed["format_compliant"]
        and expected_fact_recall == 1.0
        and section_placement_accuracy == 1.0
        and forbidden_leakage_rate == 0.0
        and contradiction_resolution_rate == 1.0
        and dedup_pass_rate == 1.0
        and not extra_sections
        and compactness_pass
    )

    judge = {}
    if not skip_judge:
        judge_output, judge_latency = await run_model(judge_model, build_compaction_judge_prompt(case, output))
        judge = parse_json_object(judge_output)
        judge["latency_ms"] = round(judge_latency)

    return {
        "name": case["name"],
        "family": case["family"],
        "difficulty": case["difficulty"],
        "variant": variant,
        "latency_ms": round(latency_ms),
        "memory_output": output,
        "headings": parsed["headings"],
        "bullet_count": bullet_count,
        "format_compliant": parsed["format_compliant"],
        "section_order_compliant": parsed["order_ok"],
        "expected_fact_recall": round(expected_fact_recall, 3),
        "forbidden_hits": forbidden_hits,
        "forbidden_leakage_rate": round(forbidden_leakage_rate, 3),
        "contradiction_resolution_rate": round(contradiction_resolution_rate, 3),
        "dedup_pass_rate": round(dedup_pass_rate, 3),
        "section_placement_accuracy": round(section_placement_accuracy, 3),
        "empty_section_suppression_correct": not extra_sections,
        "extra_sections": extra_sections,
        "compactness_pass": compactness_pass,
        "extra_lines": parsed["extra_lines"],
        "deterministic_pass": deterministic_pass,
        "judge": judge,
    }


async def evaluate_ask_case(case: dict, variant: str, model) -> dict:
    conversation_history = format_conversation_messages(case["recent_history"])
    context_text = format_rag_context(case["rag_context"])
    prompt = (
        build_baseline_ask_prompt(case["question"], case["user_memory"], conversation_history, context_text)
        if variant == "baseline"
        else build_ask_prompt(case["question"], case["user_memory"], conversation_history, context_text)
    )
    answer, latency_ms = await run_model(model, prompt)
    expected_hits = [contains_any(answer, item) for item in case["expected_keywords"]]
    keyword_recall = sum(expected_hits) / len(expected_hits) if expected_hits else 1.0
    forbidden_hits = [item for item in case["forbidden_keywords"] if contains_any(answer, item)]
    hallucination_score = 1.0 - (len(forbidden_hits) / len(case["forbidden_keywords"])) if case["forbidden_keywords"] else 1.0
    honesty_pass = True
    if case["expected_source_behavior"] == "unsupported_honesty":
        honesty_pass = any(contains_any(answer, marker) for marker in HONESTY_MARKERS)
    precedence_correct = keyword_recall == 1.0 and not forbidden_hits and honesty_pass
    return {
        "name": case["name"],
        "family": case["family"],
        "difficulty": case["difficulty"],
        "variant": variant,
        "latency_ms": round(latency_ms),
        "answer": answer,
        "memory_keyword_recall": round(keyword_recall, 3),
        "forbidden_hits": forbidden_hits,
        "hallucination_score": round(hallucination_score, 3),
        "honesty_pass": honesty_pass,
        "precedence_correct": precedence_correct,
        "deterministic_pass": precedence_correct,
        "expected_source_behavior": case["expected_source_behavior"],
    }


def summarize_group(rows: list[dict], pass_key: str) -> dict:
    return {
        "count": len(rows),
        "pass_rate": round(sum(1 for row in rows if row[pass_key]) / len(rows), 3),
    } if rows else {"count": 0, "pass_rate": 0.0}


def summarize_compaction(results: list[dict]) -> dict:
    latencies = [row["latency_ms"] for row in results]
    summary = {
        "cases": len(results),
        "format_compliance_rate": round(sum(row["format_compliant"] for row in results) / len(results), 3),
        "section_order_compliance_rate": round(sum(row["section_order_compliant"] for row in results) / len(results), 3),
        "avg_expected_fact_recall": round(statistics.mean(row["expected_fact_recall"] for row in results), 3),
        "avg_forbidden_leakage_rate": round(statistics.mean(row["forbidden_leakage_rate"] for row in results), 3),
        "avg_contradiction_resolution_rate": round(statistics.mean(row["contradiction_resolution_rate"] for row in results), 3),
        "avg_dedup_pass_rate": round(statistics.mean(row["dedup_pass_rate"] for row in results), 3),
        "avg_section_placement_accuracy": round(statistics.mean(row["section_placement_accuracy"] for row in results), 3),
        "empty_section_suppression_rate": round(sum(row["empty_section_suppression_correct"] for row in results) / len(results), 3),
        "compactness_pass_rate": round(sum(row["compactness_pass"] for row in results) / len(results), 3),
        "deterministic_pass_rate": round(sum(row["deterministic_pass"] for row in results) / len(results), 3),
        "avg_latency_ms": round(statistics.mean(latencies)),
        "p95_latency_ms": round(percentile(latencies, 0.95)),
    }
    judged = [row["judge"] for row in results if row["judge"]]
    if judged:
        summary["judge_avg"] = {
            metric: round(statistics.mean(row.get(metric, 0) for row in judged), 3)
            for metric in ["faithfulness", "merge_quality", "contradiction_handling", "conciseness", "usefulness"]
        }
    by_family = defaultdict(list)
    by_difficulty = defaultdict(list)
    for row in results:
        by_family[row["family"]].append(row)
        by_difficulty[row["difficulty"]].append(row)
    summary["by_family"] = {key: summarize_group(value, "deterministic_pass") for key, value in sorted(by_family.items())}
    summary["by_difficulty"] = {key: summarize_group(value, "deterministic_pass") for key, value in sorted(by_difficulty.items())}
    return summary


def summarize_ask(results: list[dict]) -> dict:
    latencies = [row["latency_ms"] for row in results]
    summary = {
        "cases": len(results),
        "avg_memory_keyword_recall": round(statistics.mean(row["memory_keyword_recall"] for row in results), 3),
        "avg_hallucination_score": round(statistics.mean(row["hallucination_score"] for row in results), 3),
        "precedence_correct_rate": round(sum(row["precedence_correct"] for row in results) / len(results), 3),
        "honesty_pass_rate": round(sum(row["honesty_pass"] for row in results) / len(results), 3),
        "deterministic_pass_rate": round(sum(row["deterministic_pass"] for row in results) / len(results), 3),
        "avg_latency_ms": round(statistics.mean(latencies)),
        "p95_latency_ms": round(percentile(latencies, 0.95)),
    }
    by_family = defaultdict(list)
    by_difficulty = defaultdict(list)
    for row in results:
        by_family[row["family"]].append(row)
        by_difficulty[row["difficulty"]].append(row)
    summary["by_family"] = {key: summarize_group(value, "deterministic_pass") for key, value in sorted(by_family.items())}
    summary["by_difficulty"] = {key: summarize_group(value, "deterministic_pass") for key, value in sorted(by_difficulty.items())}
    return summary


def print_summary(title: str, summary: dict) -> None:
    print("=" * 80)
    print(title)
    print("=" * 80)
    for key, value in summary.items():
        if key in {"by_family", "by_difficulty", "judge_avg"}:
            continue
        print(f"{key}: {value}")
    if "judge_avg" in summary:
        print("judge_avg:")
        for key, value in summary["judge_avg"].items():
            print(f"  {key}: {value}")
    print("by_family:")
    for key, value in summary["by_family"].items():
        print(f"  {key}: {value}")
    print("by_difficulty:")
    for key, value in summary["by_difficulty"].items():
        print(f"  {key}: {value}")


def print_worst_cases(title: str, results: list[dict], mode: str) -> None:
    print("-" * 80)
    print(title)
    print("-" * 80)
    if mode == "compaction":
        ranked = sorted(results, key=lambda row: (row["deterministic_pass"], row["expected_fact_recall"], -row["forbidden_leakage_rate"]))[:5]
        for row in ranked:
            print(f"{row['name']} | family={row['family']} | pass={row['deterministic_pass']} | recall={row['expected_fact_recall']} | leakage={row['forbidden_leakage_rate']}")
            if row["forbidden_hits"]:
                print(f"  forbidden_hits: {row['forbidden_hits']}")
            if row["extra_lines"]:
                print(f"  extra_lines: {row['extra_lines']}")
            print(f"  output: {row['memory_output'][:220]}")
    else:
        ranked = sorted(results, key=lambda row: (row["deterministic_pass"], row["memory_keyword_recall"], row["hallucination_score"]))[:5]
        for row in ranked:
            print(f"{row['name']} | family={row['family']} | pass={row['deterministic_pass']} | recall={row['memory_keyword_recall']} | hallucination={row['hallucination_score']}")
            if row["forbidden_hits"]:
                print(f"  forbidden_hits: {row['forbidden_hits']}")
            print(f"  answer: {row['answer'][:220]}")


async def run_suite(args) -> dict:
    load_dotenv()
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is required to run memory_compaction_evaluation.py")

    variants = ["baseline", "tuned"] if args.variant == "both" else [args.variant]
    model = ChatGoogleGenerativeAI(model=args.model, temperature=0.1)
    judge_model_name = args.judge_model or args.model
    judge_model = ChatGoogleGenerativeAI(model=judge_model_name, temperature=0.0)

    report = {
        "config": {
            "mode": args.mode,
            "variant": args.variant,
            "model": args.model,
            "judge_model": judge_model_name,
            "skip_judge": args.skip_judge,
        },
        "compaction": {},
        "ask": {},
    }

    for variant in variants:
        if args.mode in {"compaction", "all"}:
            results = []
            print(f"\nRunning compaction suite for variant={variant} ({len(COMPACTION_CASES)} cases)")
            for index, case in enumerate(COMPACTION_CASES, 1):
                print(f"  [{index}/{len(COMPACTION_CASES)}] {case['name']}")
                results.append(
                    await evaluate_compaction_case(case, variant, model, judge_model, args.skip_judge)
                )
            summary = summarize_compaction(results)
            report["compaction"][variant] = {"summary": summary, "results": results}
            print_summary(f"Compaction Summary ({variant})", summary)
            print_worst_cases(f"Worst Compaction Cases ({variant})", results, "compaction")

        if args.mode in {"ask", "all"}:
            results = []
            print(f"\nRunning ask suite for variant={variant} ({len(ASK_CASES)} cases)")
            for index, case in enumerate(ASK_CASES, 1):
                print(f"  [{index}/{len(ASK_CASES)}] {case['name']}")
                results.append(await evaluate_ask_case(case, variant, model))
            summary = summarize_ask(results)
            report["ask"][variant] = {"summary": summary, "results": results}
            print_summary(f"Ask Summary ({variant})", summary)
            print_worst_cases(f"Worst Ask Cases ({variant})", results, "ask")

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(f"\nSaved detailed results to {args.output}")
    return report


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate Ask memory compaction and Ask memory usage.")
    parser.add_argument("--mode", choices=["compaction", "ask", "all"], default="all")
    parser.add_argument("--variant", choices=["baseline", "tuned", "both"], default="tuned")
    parser.add_argument("--model", default="gemini-2.5-flash-lite")
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--output", default=RESULTS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_suite(parse_args()))
