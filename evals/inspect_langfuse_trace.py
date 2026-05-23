"""Inspect a single Langfuse trace or observation in detail.

Prints the full observation tree (parent + children) with input, output, usage,
latency, and any error/status info. Useful for diagnosing anomalous traces
surfaced by the diff script.

Usage:
    python -m evals.inspect_langfuse_trace --trace-id 83cd7552d62b160c20d63ad1948a9cc1
    python -m evals.inspect_langfuse_trace --observation-id 64a36cfd2ad1fa78

Env vars (same as the rest of the app):
    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

load_dotenv(encoding="utf-8-sig")

try:
    from langfuse import Langfuse
except ImportError as exc:
    print(f"ERROR: langfuse package required: {exc}", file=sys.stderr)
    sys.exit(1)


def _truncate(value, max_chars: int = 2000) -> str:
    if value is None:
        return "None"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated, total {len(text)} chars]"


def _obs_to_dict(obs) -> dict:
    return {
        "id": getattr(obs, "id", None),
        "trace_id": getattr(obs, "trace_id", None),
        "parent_observation_id": getattr(obs, "parent_observation_id", None),
        "type": getattr(obs, "type", None),
        "name": getattr(obs, "name", None),
        "start_time": getattr(obs, "start_time", None),
        "end_time": getattr(obs, "end_time", None),
        "latency": getattr(obs, "latency", None),
        "model": getattr(obs, "model", None),
        "model_parameters": getattr(obs, "model_parameters", None),
        "usage_details": getattr(obs, "usage_details", None),
        "cost_details": getattr(obs, "cost_details", None),
        "total_cost": getattr(obs, "total_cost", None),
        "level": getattr(obs, "level", None),
        "status_message": getattr(obs, "status_message", None),
        "input": getattr(obs, "input", None),
        "output": getattr(obs, "output", None),
        "metadata": getattr(obs, "metadata", None),
    }


def print_observation(obs_dict: dict, depth: int = 0) -> None:
    pad = "  " * depth
    type_label = obs_dict.get("type") or "?"
    name = obs_dict.get("name") or "(unnamed)"
    latency = obs_dict.get("latency")
    latency_str = f"{float(latency) * 1000:.1f}ms" if latency is not None else "—"
    print(f"{pad}[{type_label}] {name}  ({latency_str})")
    print(f"{pad}  id              : {obs_dict.get('id')}")
    print(f"{pad}  parent_id       : {obs_dict.get('parent_observation_id') or '(root)'}")
    print(f"{pad}  start / end     : {obs_dict.get('start_time')} -> {obs_dict.get('end_time')}")
    if obs_dict.get("model"):
        print(f"{pad}  model           : {obs_dict.get('model')}")
    if obs_dict.get("model_parameters"):
        print(f"{pad}  model_params    : {_truncate(obs_dict.get('model_parameters'), 400)}")
    if obs_dict.get("usage_details"):
        print(f"{pad}  usage_details   : {obs_dict.get('usage_details')}")
    if obs_dict.get("cost_details") or obs_dict.get("total_cost"):
        print(f"{pad}  cost            : total={obs_dict.get('total_cost')} details={obs_dict.get('cost_details')}")
    if obs_dict.get("level") and str(obs_dict.get("level")).upper() != "DEFAULT":
        print(f"{pad}  level           : {obs_dict.get('level')}")
    if obs_dict.get("status_message"):
        print(f"{pad}  status_message  : {obs_dict.get('status_message')}")
    if obs_dict.get("metadata"):
        print(f"{pad}  metadata        : {_truncate(obs_dict.get('metadata'), 600)}")
    if obs_dict.get("input") is not None:
        print(f"{pad}  input           : {_truncate(obs_dict.get('input'))}")
    if obs_dict.get("output") is not None:
        print(f"{pad}  output          : {_truncate(obs_dict.get('output'))}")


def build_tree(observations: list[dict]) -> dict:
    """Return {parent_id_or_None: [child_dict, ...]} for tree traversal."""
    by_parent: dict = {}
    for obs in observations:
        parent = obs.get("parent_observation_id")
        by_parent.setdefault(parent, []).append(obs)
    # Sort children by start_time for readable output.
    for kids in by_parent.values():
        kids.sort(key=lambda o: (o.get("start_time") or ""))
    return by_parent


def walk(by_parent: dict, parent_id, depth: int = 0) -> None:
    for child in by_parent.get(parent_id, []):
        print_observation(child, depth=depth)
        print()
        walk(by_parent, child.get("id"), depth=depth + 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a Langfuse trace or observation.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--trace-id", help="Trace ID to fetch (preferred — returns all observations inline).")
    group.add_argument(
        "--observation-id",
        help="Observation ID; the tool resolves its trace and walks from there.",
    )
    args = parser.parse_args()

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not public_key or not secret_key:
        raise SystemExit("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set.")

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    trace_id = args.trace_id
    focal_observation_id = None
    if args.observation_id:
        focal_observation_id = args.observation_id
        resp = client.api.observations.get_many(
            fields="core,basic", limit=1, parent_observation_id=None,
        )
        # Lookup via direct ID fetch isn't exposed cleanly; use trace lookup.
        # The observation fetch is available via the API but only by paged search.
        # Simpler: query observations by id via filter or fetch the observation's trace.
        obs_detail = client.api.observations.get_many(
            fields="core,basic",
            filter=json.dumps([
                {"column": "id", "type": "string", "operator": "=", "value": args.observation_id}
            ]),
            limit=1,
        )
        if not obs_detail.data:
            raise SystemExit(f"Observation {args.observation_id} not found.")
        trace_id = obs_detail.data[0].trace_id

    print("=" * 100)
    print(f"LANGFUSE TRACE INSPECT — {trace_id}")
    if focal_observation_id:
        print(f"(resolved from observation_id={focal_observation_id})")
    print("=" * 100)

    trace = client.api.trace.get(trace_id=trace_id)

    trace_summary = {
        "id": trace.id,
        "timestamp": trace.timestamp,
        "name": trace.name,
        "user_id": trace.user_id,
        "session_id": trace.session_id,
        "environment": trace.environment,
        "tags": trace.tags,
        "latency": trace.latency,
        "total_cost": trace.total_cost,
        "input": trace.input,
        "output": trace.output,
        "metadata": trace.metadata,
        "html_path": trace.html_path,
    }

    print("\n--- TRACE ---")
    for key, value in trace_summary.items():
        if key in ("input", "output", "metadata"):
            print(f"  {key:14} : {_truncate(value, 1500)}")
        else:
            print(f"  {key:14} : {value}")

    observations = [_obs_to_dict(o) for o in (trace.observations or [])]
    print(f"\n--- OBSERVATIONS ({len(observations)}) ---")
    if not observations:
        print("  (no observations on this trace)")
    else:
        by_parent = build_tree(observations)
        # Roots: parent_id None or pointing to something not in this trace.
        present_ids = {o["id"] for o in observations}
        roots = []
        for obs in observations:
            parent_id = obs.get("parent_observation_id")
            if parent_id is None or parent_id not in present_ids:
                roots.append(obs)
        roots.sort(key=lambda o: (o.get("start_time") or ""))
        for root in roots:
            print_observation(root, depth=0)
            print()
            walk(by_parent, root["id"], depth=1)

    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"trace_inspect_{trace_id}.json"
    payload = {
        "fetched_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "trace": trace_summary,
        "observations": observations,
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
    print(f"\nWrote raw JSON to {out_path}")


if __name__ == "__main__":
    main()
