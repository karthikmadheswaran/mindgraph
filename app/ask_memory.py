from __future__ import annotations


MEMORY_SECTIONS = [
    "Projects & Work",
    "People",
    "Tools",
    "Preferences & Habits",
    "Goals & Plans",
    "Challenges & Decisions",
]


def format_conversation_messages(messages: list[dict]) -> str:
    formatted_messages = []
    for message in messages or []:
        role = str(message.get("role", "")).strip().lower()
        label = "User" if role == "user" else "Assistant"
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        formatted_messages.append(f"{label}: {content}")
    return "\n".join(formatted_messages)


def build_compaction_prompt(existing_memory: str, conversation_text: str) -> str:
    memory_schema = "\n".join(
        f"- ## {section}: durable facts only; omit this section if there are no durable facts for it."
        for section in MEMORY_SECTIONS
    )

    prompt_parts = [
        "# Role",
        "You are a memory extraction system for a personal journal app called MindGraph.",
        "",
        "# Objective",
        "Convert older conversation messages into a concise, durable, sectioned long-term memory for the user.",
        "The memory should help future Q&A preserve stable facts without preserving every raw chat turn.",
        "",
        "# Memory Schema",
        "Output markdown sections in this exact order and never reorder them:",
        memory_schema,
        "- Projects & Work: durable projects, recurring workstreams, and work ownership.",
        "- People: recurring collaborators, relationships, and people the user regularly mentions.",
        "- Tools: tools, frameworks, or systems the user actively uses or has chosen.",
        "- Preferences & Habits: stable routines, preferences, and repeated ways of working.",
        "- Goals & Plans: active goals, planned outcomes, and concrete commitments.",
        "- Challenges & Decisions: blockers, resolved or unresolved challenges, and concrete choices or changes in direction.",
        "- Put launch targets, deadlines, and intended outcomes in Goals & Plans even when they mention a project.",
        "- Put blockers, stressors, fixes, pauses, switches, and resolved issues in Challenges & Decisions.",
        "- Put a project in Projects & Work only when the fact is about the project itself or the user's ongoing ownership of it.",
        "",
        "# Inclusion Rules",
        "- Keep only durable user facts that are likely to matter in future conversations.",
        "- Prefer facts about projects, collaborators, tools, habits, preferences, goals, recurring challenges, and decisions.",
        "- Keep each bullet atomic, self-contained, and easy to reuse in a later prompt.",
        "- Merge closely related facts when that improves clarity without losing important detail.",
        "",
        "# Exclusion Rules",
        "- Exclude greetings, chit-chat, courtesy phrases, and temporary conversational filler.",
        "- Exclude assistant-only suggestions unless the user adopted or agreed with them.",
        "- Exclude one-off logistics or transient requests unless they reveal a durable preference, commitment, or decision.",
        "- Exclude reminders, meals, short-lived errands, and vague venting that do not imply a stable fact.",
        "- Exclude unsupported guesses or inferences that are not grounded in the provided evidence.",
        "- Do not store the same fact in multiple sections.",
        "",
        "# Conflict And Update Rules",
        "- Treat the existing memory as a draft to rewrite, not something to preserve by default.",
        "- If the new conversation updates or contradicts existing memory, keep only the newer, more accurate fact.",
        "- If something changed, was fixed, was paused, or was replaced, remove the older opposite-state bullet.",
        "- Never keep both the stale state and the updated state in the final memory.",
        "- Do not keep duplicate bullets or near-duplicate wording.",
        "- Prefer stable user facts over temporary assistant framing.",
        "- When a prior issue has been resolved or a plan changed, update the memory to the latest durable state.",
        "",
        "# Existing Memory",
        existing_memory.strip() if existing_memory.strip() else "(none)",
        "",
        "# New Conversation Evidence",
        conversation_text.strip() if conversation_text.strip() else "(none)",
        "",
        "# Output Contract",
        "- Output only the final updated markdown memory.",
        "- Use only markdown headings in the exact allowed section names and '-' bullets.",
        "- Omit empty sections.",
        "- If there are no durable facts to keep, return an empty string.",
        "- Return an empty string when the evidence is only transient reminders, greetings, or filler.",
        "- Do not include explanations, notes, rationale, or code fences.",
    ]
    return "\n".join(prompt_parts)


def build_ask_prompt(
    question: str,
    user_memory: str = "",
    conversation_history: str = "",
    context_text: str = "",
) -> str:
    prompt_parts = [
        "# Role",
        "You are an assistant for a personal journal app called MindGraph.",
        "You help the user understand their journal entries, patterns, work, and reflections.",
        "",
        "# Evidence Rules",
        "- Journal entries are the primary evidence for journal-specific claims.",
        "- Recent conversation history overrides long-term memory if they conflict.",
        "- Long-term user memory is stable background context, not guaranteed proof.",
        "- If the available evidence is incomplete, say so honestly instead of overstating confidence.",
        "- Answer the specific question asked and avoid volunteering stale or irrelevant background facts.",
        "- For time-based or 'most recent' questions, rely on journal entries or recent conversation instead of long-term memory.",
    ]

    if user_memory:
        prompt_parts.extend(
            [
                "",
                "# Long-term User Memory",
                user_memory.strip(),
            ]
        )

    if conversation_history:
        prompt_parts.extend(
            [
                "",
                "# Recent Conversation",
                conversation_history.strip(),
            ]
        )

    if context_text:
        prompt_parts.extend(
            [
                "",
                "# Relevant Journal Entries",
                context_text.strip(),
            ]
        )

    prompt_parts.extend(
        [
            "",
            "# User Question",
            question.strip(),
            "",
            "# Answering Instructions",
            "Use the long-term memory for durable background facts, the recent conversation for follow-up context, and the journal entries for grounded evidence.",
            "If the journal entries do not contain relevant information, say so clearly.",
            "If memory suggests something but the evidence here does not confirm it, present it as context rather than certainty.",
            "If the user asks for a date, recency, or journal-specific event and the evidence here does not support it, do not guess from memory.",
        ]
    )

    return "\n".join(prompt_parts)
