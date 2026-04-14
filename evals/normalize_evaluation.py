import asyncio
import json
import re
import statistics
import time
from collections import defaultdict
from datetime import date, datetime, timezone

import app.nodes.normalize as normalize_module
from app.nodes.normalize import (
    build_normalize_prompt,
    generate_calendar_reference,
    normalize,
    resolve_user_timezone,
)


USER_ID = "0f5acdab-736f-4f44-883e-c897145a5ff2"
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
FORMAT_LEAK_MARKERS = [
    "```",
    "original text:",
    "cleaned text:",
    "normalized text:",
]


def utc_dt(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def make_case(
    name: str,
    family: str,
    difficulty: str,
    raw_text: str,
    expected_output: str,
    expected_dates: list[str],
    must_contain: list[str] | None = None,
    must_not_contain: list[str] | None = None,
    reference_utc: datetime | None = None,
    user_timezone: str = "UTC",
) -> dict:
    return {
        "name": name,
        "family": family,
        "difficulty": difficulty,
        "raw_text": raw_text,
        "expected_output": expected_output,
        "expected_dates": expected_dates,
        "must_contain": must_contain or [],
        "must_not_contain": must_not_contain or [],
        "reference_utc": reference_utc or utc_dt(2026, 4, 9, 12, 0),
        "user_timezone": user_timezone,
    }


TEST_CASES = [
    make_case(
        name="absolute_date_passthrough",
        family="absolute_preservation",
        difficulty="easy",
        raw_text="Need to submit the report on 2026-04-12",
        expected_output="Need to submit the report on 2026-04-12.",
        expected_dates=["2026-04-12"],
        must_contain=["submit", "report"],
    ),
    make_case(
        name="tomorrow_basic",
        family="relative_day",
        difficulty="easy",
        raw_text="Need to call mom tomorrow",
        expected_output="Need to call mom on 2026-04-10.",
        expected_dates=["2026-04-10"],
        must_contain=["call", "mom"],
        must_not_contain=["tomorrow"],
    ),
    make_case(
        name="next_monday_known_bug",
        family="weekday_lookup",
        difficulty="medium",
        raw_text="gave me a deadline to go from next monday",
        expected_output="gave me a deadline to go from 2026-04-13",
        expected_dates=["2026-04-13"],
        must_contain=["deadline"],
        must_not_contain=["next monday"],
    ),
    make_case(
        name="by_friday_same_week",
        family="weekday_lookup",
        difficulty="easy",
        raw_text="Meeting with Rahul by friday",
        expected_output="Meeting with Rahul by 2026-04-10.",
        expected_dates=["2026-04-10"],
        must_contain=["meeting", "rahul"],
        must_not_contain=["by friday"],
    ),
    make_case(
        name="last_tuesday_lookup",
        family="weekday_lookup",
        difficulty="easy",
        raw_text="Started the project last tuesday",
        expected_output="Started the project on 2026-04-07.",
        expected_dates=["2026-04-07"],
        must_contain=["started", "project"],
        must_not_contain=["last tuesday"],
    ),
    make_case(
        name="in_three_days_offset",
        family="relative_offset",
        difficulty="medium",
        raw_text="Doctor appointment in 3 days",
        expected_output="Doctor appointment on 2026-04-12.",
        expected_dates=["2026-04-12"],
        must_contain=["doctor", "appointment"],
        must_not_contain=["in 3 days"],
    ),
    make_case(
        name="two_weeks_from_now",
        family="relative_offset",
        difficulty="medium",
        raw_text="Pay rent two weeks from now",
        expected_output="Pay rent on 2026-04-23.",
        expected_dates=["2026-04-23"],
        must_contain=["pay", "rent"],
        must_not_contain=["two weeks from now"],
    ),
    make_case(
        name="in_ten_days",
        family="relative_offset",
        difficulty="hard",
        raw_text="Need to move house in 10 days",
        expected_output="Need to move house on 2026-04-19.",
        expected_dates=["2026-04-19"],
        must_contain=["move", "house"],
        must_not_contain=["in 10 days"],
    ),
    make_case(
        name="end_of_next_month",
        family="relative_month",
        difficulty="hard",
        raw_text="Need to finish taxes by the end of next month",
        expected_output="Need to finish taxes by 2026-05-31.",
        expected_dates=["2026-05-31"],
        must_contain=["finish", "taxes"],
        must_not_contain=["end of next month"],
    ),
    make_case(
        name="multiple_relative_dates",
        family="multi_date",
        difficulty="medium",
        raw_text="Need to call mom tomorrow and meet Rahul next monday",
        expected_output="Need to call mom on 2026-04-10 and meet Rahul on 2026-04-13.",
        expected_dates=["2026-04-10", "2026-04-13"],
        must_contain=["call", "mom", "meet", "rahul"],
        must_not_contain=["tomorrow", "next monday"],
    ),
    make_case(
        name="mixed_absolute_and_relative",
        family="multi_date",
        difficulty="medium",
        raw_text="Pay rent on 2026-04-30 and call Arun tomorrow",
        expected_output="Pay rent on 2026-04-30 and call Arun on 2026-04-10.",
        expected_dates=["2026-04-10", "2026-04-30"],
        must_contain=["pay", "rent", "call", "arun"],
        must_not_contain=["tomorrow"],
    ),
    make_case(
        name="offset_plus_absolute",
        family="multi_date",
        difficulty="hard",
        raw_text="Send invoice in 3 days, demo on 2026-04-20",
        expected_output="Send invoice on 2026-04-12, demo on 2026-04-20.",
        expected_dates=["2026-04-12", "2026-04-20"],
        must_contain=["send", "invoice", "demo"],
        must_not_contain=["in 3 days"],
    ),
    make_case(
        name="slang_tomorrow_projectx",
        family="cleanup",
        difficulty="medium",
        raw_text="gonna meet rahul tmrw abt projectx",
        expected_output="Going to meet Rahul on 2026-04-10 about ProjectX.",
        expected_dates=["2026-04-10"],
        must_contain=["meet", "rahul", "projectx"],
        must_not_contain=["gonna", "tmrw", "abt"],
    ),
    make_case(
        name="typo_next_monday",
        family="cleanup",
        difficulty="hard",
        raw_text="hav to submit visa docs nxt monday",
        expected_output="Have to submit visa docs on 2026-04-13.",
        expected_dates=["2026-04-13"],
        must_contain=["submit", "visa", "docs"],
        must_not_contain=["hav", "nxt monday", "nxt"],
    ),
    make_case(
        name="slang_multiple_dates",
        family="cleanup",
        difficulty="hard",
        raw_text="tmrw gotta mail Priya and nxt monday demo projectx",
        expected_output="Tomorrow have to mail Priya on 2026-04-10 and demo ProjectX on 2026-04-13.",
        expected_dates=["2026-04-10", "2026-04-13"],
        must_contain=["mail", "priya", "demo", "projectx"],
        must_not_contain=["tmrw", "gotta", "nxt monday", "nxt"],
    ),
    make_case(
        name="no_date_future_hope",
        family="no_date",
        difficulty="easy",
        raw_text="Someday I want to move cities",
        expected_output="Someday I want to move cities.",
        expected_dates=[],
        must_contain=["move", "cities"],
    ),
    make_case(
        name="no_date_change_life",
        family="no_date",
        difficulty="easy",
        raw_text="I need to change my life soon",
        expected_output="I need to change my life soon.",
        expected_dates=[],
        must_contain=["change", "life"],
    ),
    make_case(
        name="no_date_emotional_noise",
        family="no_date",
        difficulty="easy",
        raw_text="Life feels messy but I am trying my best",
        expected_output="Life feels messy but I am trying my best.",
        expected_dates=[],
        must_contain=["life", "messy", "trying"],
    ),
    make_case(
        name="month_boundary_next_monday",
        family="boundary",
        difficulty="hard",
        raw_text="Need to submit the draft next monday",
        expected_output="Need to submit the draft on 2026-02-02.",
        expected_dates=["2026-02-02"],
        must_contain=["submit", "draft"],
        must_not_contain=["next monday"],
        reference_utc=utc_dt(2026, 1, 29, 12, 0),
    ),
    make_case(
        name="year_boundary_tomorrow",
        family="boundary",
        difficulty="medium",
        raw_text="Need to call mom tomorrow",
        expected_output="Need to call mom on 2027-01-01.",
        expected_dates=["2027-01-01"],
        must_contain=["call", "mom"],
        must_not_contain=["tomorrow"],
        reference_utc=utc_dt(2026, 12, 31, 12, 0),
    ),
    make_case(
        name="year_boundary_next_monday",
        family="boundary",
        difficulty="hard",
        raw_text="Project review next monday",
        expected_output="Project review on 2027-01-04.",
        expected_dates=["2027-01-04"],
        must_contain=["project", "review"],
        must_not_contain=["next monday"],
        reference_utc=utc_dt(2026, 12, 31, 12, 0),
    ),
    make_case(
        name="last_friday_from_monday",
        family="boundary",
        difficulty="medium",
        raw_text="Started the sprint last friday",
        expected_output="Started the sprint on 2026-03-27.",
        expected_dates=["2026-03-27"],
        must_contain=["started", "sprint"],
        must_not_contain=["last friday"],
        reference_utc=utc_dt(2026, 3, 30, 12, 0),
    ),
    make_case(
        name="timezone_asia_kolkata_tomorrow",
        family="timezone",
        difficulty="hard",
        raw_text="Need to call mom tomorrow",
        expected_output="Need to call mom on 2026-04-11.",
        expected_dates=["2026-04-11"],
        must_contain=["call", "mom"],
        must_not_contain=["tomorrow"],
        reference_utc=utc_dt(2026, 4, 9, 23, 30),
        user_timezone="Asia/Kolkata",
    ),
    make_case(
        name="timezone_new_york_tomorrow",
        family="timezone",
        difficulty="hard",
        raw_text="Need to call mom tomorrow",
        expected_output="Need to call mom on 2026-04-10.",
        expected_dates=["2026-04-10"],
        must_contain=["call", "mom"],
        must_not_contain=["tomorrow"],
        reference_utc=utc_dt(2026, 4, 9, 23, 30),
        user_timezone="America/New_York",
    ),
    make_case(
        name="invalid_timezone_fallback",
        family="timezone",
        difficulty="hard",
        raw_text="Need to call mom tomorrow",
        expected_output="Need to call mom on 2026-04-10.",
        expected_dates=["2026-04-10"],
        must_contain=["call", "mom"],
        must_not_contain=["tomorrow"],
        reference_utc=utc_dt(2026, 4, 9, 23, 30),
        user_timezone="Mars/Phobos",
    ),
]


REAL_DATETIME = normalize_module.datetime


class FrozenDateTime(datetime):
    frozen_utc = utc_dt(2026, 4, 9, 12, 0)

    @classmethod
    def now(cls, tz=None):
        base = cls.frozen_utc
        if tz is None:
            return base.replace(tzinfo=None)
        return base.astimezone(tz)


def normalize_relaxed_text(text: str) -> str:
    value = str(text or "").lower()
    value = re.sub(r"[^a-z0-9\s\-]", "", value)
    value = " ".join(value.split())
    return value


def contains_phrase(text: str, phrase: str) -> bool:
    return normalize_relaxed_text(phrase) in normalize_relaxed_text(text)


def extract_dates(text: str) -> list[str]:
    ordered = []
    for match in DATE_RE.findall(text or ""):
        if match not in ordered:
            ordered.append(match)
    return ordered


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return ordered[index]


def build_state(case: dict) -> dict:
    return {
        "raw_text": case["raw_text"],
        "user_id": USER_ID,
        "user_timezone": case["user_timezone"],
        "cleaned_text": "",
        "auto_title": "",
        "summary": "",
        "input_type": "text",
        "attachment_url": "",
        "classifier": [],
        "core_entities": [],
        "deadline": [],
        "relations": [],
        "trigger_check": False,
        "duplicate_of": None,
        "dedup_check_result": None,
    }


def evaluate_helper_checks() -> list[dict]:
    april_calendar = generate_calendar_reference(date(2026, 4, 9))
    january_calendar = generate_calendar_reference(date(2026, 1, 29))
    december_calendar = generate_calendar_reference(date(2026, 12, 31))
    prompt = build_normalize_prompt(
        "gave me a deadline to go from next monday",
        datetime(2026, 4, 9, 10, 0, 0),
    )

    checks = [
        {
            "name": "calendar_april_next_monday",
            "passed": "Week of Apr 13: Mon=2026-04-13" in april_calendar,
        },
        {
            "name": "calendar_january_boundary",
            "passed": "Week of Feb 2: Mon=2026-02-02" in january_calendar,
        },
        {
            "name": "calendar_december_year_boundary",
            "passed": "Week of Jan 4: Mon=2027-01-04" in december_calendar,
        },
        {
            "name": "prompt_has_calendar_guidance",
            "passed": "IMPORTANT: Do NOT calculate dates yourself." in prompt,
        },
        {
            "name": "prompt_has_human_readable_today",
            "passed": "Today is Thursday, 2026-04-09." in prompt,
        },
        {
            "name": "invalid_timezone_falls_back_to_utc",
            "passed": str(resolve_user_timezone("Not/ARealZone")) == "UTC",
        },
    ]
    return checks


async def run_case(case: dict) -> dict:
    FrozenDateTime.frozen_utc = case["reference_utc"]
    state = build_state(case)

    started = time.perf_counter()
    result = await normalize(state)
    latency_ms = (time.perf_counter() - started) * 1000
    output = result["cleaned_text"]

    expected_dates = case["expected_dates"]
    predicted_dates = extract_dates(output)
    predicted_set = set(predicted_dates)
    expected_set = set(expected_dates)

    missing_required = [
        phrase for phrase in case["must_contain"] if not contains_phrase(output, phrase)
    ]
    forbidden_hits = [
        phrase for phrase in case["must_not_contain"] if contains_phrase(output, phrase)
    ]
    format_clean = not any(marker in output.lower() for marker in FORMAT_LEAK_MARKERS)

    strict_exact = output.strip() == case["expected_output"].strip()
    relaxed_exact = normalize_relaxed_text(output) == normalize_relaxed_text(case["expected_output"])

    date_tp = len(predicted_set & expected_set)
    date_fp = len(predicted_set - expected_set)
    date_fn = len(expected_set - predicted_set)

    date_set_exact = predicted_set == expected_set
    no_date_hallucination = (not expected_dates) and (not predicted_dates)
    functional_pass = (
        date_set_exact
        and not missing_required
        and not forbidden_hits
        and format_clean
    )

    return {
        "name": case["name"],
        "family": case["family"],
        "difficulty": case["difficulty"],
        "user_timezone": case["user_timezone"],
        "reference_utc": case["reference_utc"].isoformat(),
        "latency_ms": latency_ms,
        "output": output,
        "expected_output": case["expected_output"],
        "predicted_dates": predicted_dates,
        "expected_dates": expected_dates,
        "strict_exact": strict_exact,
        "relaxed_exact": relaxed_exact,
        "date_tp": date_tp,
        "date_fp": date_fp,
        "date_fn": date_fn,
        "date_set_exact": date_set_exact,
        "no_date_hallucination": no_date_hallucination,
        "missing_required": missing_required,
        "forbidden_hits": forbidden_hits,
        "format_clean": format_clean,
        "functional_pass": functional_pass,
    }


def summarize_results(results: list[dict], helper_checks: list[dict]) -> dict:
    total_cases = len(results)
    latencies = [result["latency_ms"] for result in results]

    date_tp = sum(result["date_tp"] for result in results)
    date_fp = sum(result["date_fp"] for result in results)
    date_fn = sum(result["date_fn"] for result in results)

    date_precision = date_tp / (date_tp + date_fp) if (date_tp + date_fp) else 0.0
    date_recall = date_tp / (date_tp + date_fn) if (date_tp + date_fn) else 0.0
    date_f1 = (
        (2 * date_precision * date_recall / (date_precision + date_recall))
        if (date_precision + date_recall)
        else 0.0
    )

    no_date_cases = [result for result in results if not result["expected_dates"]]
    required_total = sum(
        len(case["must_contain"]) for case in TEST_CASES
    )
    required_missing = sum(
        len(result["missing_required"]) for result in results
    )
    forbidden_total = sum(
        len(case["must_not_contain"]) for case in TEST_CASES
    )
    forbidden_hits = sum(
        len(result["forbidden_hits"]) for result in results
    )

    summary = {
        "total_cases": total_cases,
        "strict_exact_match_rate": sum(result["strict_exact"] for result in results) / total_cases,
        "relaxed_exact_match_rate": sum(result["relaxed_exact"] for result in results) / total_cases,
        "functional_pass_rate": sum(result["functional_pass"] for result in results) / total_cases,
        "date_case_accuracy": sum(result["date_set_exact"] for result in results) / total_cases,
        "single_date_accuracy": (
            sum(
                result["date_set_exact"]
                for result in results
                if len(result["expected_dates"]) == 1
            )
            / max(1, sum(1 for result in results if len(result["expected_dates"]) == 1))
        ),
        "date_precision": date_precision,
        "date_recall": date_recall,
        "date_f1": date_f1,
        "no_date_hallucination_rate": (
            sum(result["no_date_hallucination"] for result in no_date_cases)
            / max(1, len(no_date_cases))
        ),
        "keyword_preservation_recall": (
            (required_total - required_missing) / required_total
            if required_total
            else 1.0
        ),
        "relative_phrase_removal_rate": (
            (forbidden_total - forbidden_hits) / forbidden_total
            if forbidden_total
            else 1.0
        ),
        "format_cleanliness_rate": sum(result["format_clean"] for result in results) / total_cases,
        "avg_latency_ms": statistics.mean(latencies) if latencies else 0.0,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "p95_latency_ms": percentile(latencies, 0.95),
        "helper_checks_pass_rate": (
            sum(check["passed"] for check in helper_checks) / max(1, len(helper_checks))
        ),
    }

    by_family = defaultdict(list)
    by_difficulty = defaultdict(list)
    for result in results:
        by_family[result["family"]].append(result)
        by_difficulty[result["difficulty"]].append(result)

    summary["by_family"] = {
        family: {
            "cases": len(items),
            "functional_pass_rate": sum(item["functional_pass"] for item in items) / len(items),
            "date_case_accuracy": sum(item["date_set_exact"] for item in items) / len(items),
            "relaxed_exact_match_rate": sum(item["relaxed_exact"] for item in items) / len(items),
        }
        for family, items in sorted(by_family.items())
    }
    summary["by_difficulty"] = {
        difficulty: {
            "cases": len(items),
            "functional_pass_rate": sum(item["functional_pass"] for item in items) / len(items),
            "date_case_accuracy": sum(item["date_set_exact"] for item in items) / len(items),
            "relaxed_exact_match_rate": sum(item["relaxed_exact"] for item in items) / len(items),
        }
        for difficulty, items in sorted(by_difficulty.items())
    }

    summary["failures"] = [
        {
            "name": result["name"],
            "family": result["family"],
            "difficulty": result["difficulty"],
            "predicted_dates": result["predicted_dates"],
            "expected_dates": result["expected_dates"],
            "missing_required": result["missing_required"],
            "forbidden_hits": result["forbidden_hits"],
            "output": result["output"],
        }
        for result in results
        if not result["functional_pass"]
    ]

    return summary


def print_case_results(results: list[dict]) -> None:
    print("=" * 120)
    print("NORMALIZE NODE EVALUATION")
    print("=" * 120)
    for result in results:
        print(f"\nCASE: {result['name']} | family={result['family']} | difficulty={result['difficulty']}")
        print(f"timezone={result['user_timezone']} | reference_utc={result['reference_utc']}")
        print(f"latency_ms={result['latency_ms']:.1f}")
        print(f"expected_dates={result['expected_dates']}")
        print(f"predicted_dates={result['predicted_dates']}")
        print(f"strict_exact={result['strict_exact']} | relaxed_exact={result['relaxed_exact']}")
        print(f"missing_required={result['missing_required']} | forbidden_hits={result['forbidden_hits']}")
        print(f"format_clean={result['format_clean']} | functional_pass={result['functional_pass']}")
        print(f"output={result['output']}")


def print_helper_results(helper_checks: list[dict]) -> None:
    print("\n" + "=" * 120)
    print("HELPER CHECKS")
    print("=" * 120)
    for check in helper_checks:
        print(f"{check['name']}: {'PASS' if check['passed'] else 'FAIL'}")


async def main() -> None:
    helper_checks = evaluate_helper_checks()
    original_datetime = normalize_module.datetime
    normalize_module.datetime = FrozenDateTime

    try:
        results = []
        for case in TEST_CASES:
            result = await run_case(case)
            results.append(result)
    finally:
        normalize_module.datetime = original_datetime

    summary = summarize_results(results, helper_checks)

    print_case_results(results)
    print_helper_results(helper_checks)

    print("\n" + "=" * 120)
    print("SUMMARY")
    print("=" * 120)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
