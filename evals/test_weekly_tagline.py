"""Smoke tests for the weekly inner-state tagline.

Pure unit tests against `tagline_service.generate_tagline` and
`validate_tagline`. The LLM is mocked so the suite is offline.

Run:
    python evals/test_weekly_tagline.py
"""
from __future__ import annotations

import os
import sys

if "GEMINI_API_KEY" not in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ.setdefault("GEMINI_API_KEY", "stub-for-import")
os.environ.setdefault("SUPABASE_URL", "https://stub.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "stub")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.tagline_service import (  # noqa: E402
    FALLBACK,
    MAX_WORDS,
    BANNED_SUBSTRINGS,
    generate_tagline,
    validate_tagline,
)


class FakeLLM:
    """Stand-in for the Gemini Pro model. Returns a canned response."""

    def __init__(self, content: str):
        self._content = content

    def invoke(self, _prompt: str):
        class _Resp:
            def __init__(self, content: str):
                self.content = content

        return _Resp(self._content)


RICH_SUMMARIES = [
    "Long morning thinking about the freelance pitch but mostly stalled on framing.",
    "Met with Rafael about the Pune trip. Same indecision pattern.",
    "Tried to draft the Upwork bullet list. Got distracted twice within the hour.",
    "Quiet evening journaling about the avoidance loop with the dentist again.",
    "Wrote about the dentist for the fifth time. Booked nothing.",
]

THIN_SUMMARIES = ["Single short entry."]
EMPTY_SUMMARIES: list[str] = []


def _check(case_name: str, passed: bool, detail: str = "") -> bool:
    marker = "PASS" if passed else "FAIL"
    print(f"  [{marker}] {case_name}{(' - ' + detail) if detail else ''}")
    return passed


def case_empty_returns_fallback() -> bool:
    result = generate_tagline(EMPTY_SUMMARIES, llm=FakeLLM("should not be called"))
    return _check(
        "empty entries -> fallback",
        result == FALLBACK,
        f"got: {result!r}",
    )


def case_thin_returns_fallback() -> bool:
    result = generate_tagline(THIN_SUMMARIES, llm=FakeLLM("should not be called"))
    return _check(
        "thin entries (<3) -> fallback",
        result == FALLBACK,
        f"got: {result!r}",
    )


def case_rich_passes_validator() -> bool:
    llm = FakeLLM("Mostly reflective this week. Chance of avoidance by Thursday.")
    result = generate_tagline(RICH_SUMMARIES, llm=llm)
    return _check(
        "rich entries with valid LLM output -> single line under cap",
        validate_tagline(result) and result != FALLBACK,
        f"got: {result!r}",
    )


def case_exclamation_is_rejected() -> bool:
    llm = FakeLLM("High energy week! Forecast looks bright.")
    result = generate_tagline(RICH_SUMMARIES, llm=llm)
    return _check(
        "exclamation mark from LLM -> fallback",
        result == FALLBACK,
        f"got: {result!r}",
    )


def case_too_many_words_is_rejected() -> bool:
    long_output = " ".join(["word"] * (MAX_WORDS + 2))
    llm = FakeLLM(long_output)
    result = generate_tagline(RICH_SUMMARIES, llm=llm)
    return _check(
        f">{MAX_WORDS} words -> fallback",
        result == FALLBACK,
        f"got: {result!r}",
    )


def case_motivational_phrase_is_rejected() -> bool:
    llm = FakeLLM("Time to crush it on your goals this week.")
    result = generate_tagline(RICH_SUMMARIES, llm=llm)
    return _check(
        "motivational phrase (denylist hit) -> fallback",
        result == FALLBACK,
        f"got: {result!r}",
    )


def case_validator_accepts_reference() -> bool:
    ref = "Mostly reflective this week. Chance of avoidance by Thursday."
    return _check(
        "validator accepts the brief's reference line",
        validate_tagline(ref),
        f"line: {ref!r}",
    )


def case_validator_rejects_banned_subset() -> bool:
    # Ensure each banned substring still trips the validator on a realistic line.
    failures: list[str] = []
    for phrase in BANNED_SUBSTRINGS:
        sample = f"This week feels like a {phrase} kind of stretch."
        if validate_tagline(sample):
            failures.append(phrase)
    return _check(
        "validator rejects every denylist phrase",
        not failures,
        f"missed: {failures}" if failures else "",
    )


CASES = [
    case_empty_returns_fallback,
    case_thin_returns_fallback,
    case_rich_passes_validator,
    case_exclamation_is_rejected,
    case_too_many_words_is_rejected,
    case_motivational_phrase_is_rejected,
    case_validator_accepts_reference,
    case_validator_rejects_banned_subset,
]


def main() -> int:
    print("Weekly tagline smoke tests")
    print("=" * 50)
    passed = sum(1 for case in CASES if case())
    total = len(CASES)
    print("-" * 50)
    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
