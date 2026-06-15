# app/llm.py
import os

from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")
if os.getenv("GEMINI_API_KEY"):
    # AI Studio path uses GOOGLE_API_KEY. Only set when a key exists — Vertex needs
    # none, and assigning None would crash at import in a Vertex-only deployment.
    os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY"))

# Provider toggle. When USE_VERTEX is truthy, all chat models run through Vertex AI
# (billed via Google Cloud), same Gemini models — no AI Studio prepay involved.
# Default (unset) keeps the AI Studio API-key path. Requires: langchain-google-vertexai,
# auth (service-account via GOOGLE_CREDENTIALS_JSON in prod, or local gcloud ADC), the
# Vertex AI API enabled on VERTEX_PROJECT, and gemini-2.5-* available in VERTEX_LOCATION.
_USE_VERTEX = os.getenv("USE_VERTEX", "").strip().lower() in ("1", "true", "yes")

if _USE_VERTEX:
    # Materialize a service-account key (GOOGLE_CREDENTIALS_JSON) into ADC BEFORE the
    # first ChatVertexAI is constructed — required on hosts without gcloud ADC (Railway).
    # No-op locally, where it falls back to existing ADC. Import order matters: this
    # MUST run before the client below, or the client builds with no credentials.
    from app.gcp_credentials import ensure_adc

    ensure_adc()

    from langchain_google_vertexai import ChatVertexAI

    _VERTEX_KW = dict(
        project=os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("VERTEX_LOCATION", "us-central1"),
        max_retries=2,
    )
    # thinking_budget=0 mirrors the AI Studio path (eval 23/05: 0 strictly dominates
    # 512 and -1). An earlier note here claimed ChatVertexAI doesn't take the kwarg —
    # stale: the installed langchain-google-vertexai supports it. Leaving Vertex on
    # its default DYNAMIC thinking caused observed pathology (11/06): flash-lite spun
    # ~350s on a routing prompt and returned ZERO output tokens, which downstream
    # parses as None → silent fallback routing after a multi-minute hang.
    flash = ChatVertexAI(
        model="gemini-2.5-flash-lite", temperature=0.1, thinking_budget=0, **_VERTEX_KW
    )
    flash_creative = ChatVertexAI(
        model="gemini-2.5-flash-lite", temperature=0.3, thinking_budget=0, **_VERTEX_KW
    )
    # pro keeps dynamic thinking — same as the AI Studio branch below.
    pro = ChatVertexAI(model="gemini-2.5-pro", temperature=0.3, **_VERTEX_KW)
else:
    from langchain_google_genai import ChatGoogleGenerativeAI

    # Pipeline nodes use flash (fast, cheap). Thinking disabled — eval (23/05/2026) showed
    # thinking_budget=0 strictly dominates 512 and -1 on the normalize node (96% pass rate,
    # zero variance, ~2x faster). All other pipeline nodes are pure pattern-matching and
    # don't need thinking either.
    flash = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.1,
        thinking_budget=0,
    )

    # Ask endpoint query rewriting uses flash with slightly higher temperature for variation
    # in rewrites. Thinking off — query rewriting is a single-shot transformation.
    flash_creative = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.3,
        thinking_budget=0,
    )

    # Insight engine uses pro for genuinely reflective tasks (weekly tagline, pattern
    # detection, forgotten projects). Dynamic thinking left ON — these tasks benefit from
    # the model considering long-term journal context before producing a single line of output.
    pro = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.3)


# ── Model-family-aware construction ─────────────────────────────────────────
# Gemini 2.5.x takes thinking_budget (int; 0 disables thinking — eval-proven,
# see 422df32 and the 23/05 A/B/C eval). Gemini 3.x REJECTS thinking_budget and
# takes thinking_level ("minimal" | "low" | "medium" | "high"); there is no
# zero level — "minimal" is the floor. Verified 11/06 against installed SDKs:
# langchain-google-vertexai 3.2.4 (latest available) has NO thinking_level
# field and the aiplatform proto lacks it too, so 3.x models route through
# ChatGoogleGenerativeAI (langchain-google-genai 4.2.1 / google-genai 2.8.0),
# which exposes thinking_level and reaches Vertex via vertexai=True.
_GEMINI3_LEVELS = ("minimal", "low", "medium", "high")


def _is_gemini3(model: str) -> bool:
    return model.strip().lower().startswith("gemini-3")


def build_chat_model(model: str, temperature: float = 0.1, thinking: str = ""):
    """Family-aware chat-model constructor honoring the USE_VERTEX toggle.

    `thinking`: for 2.5.x an int-like budget string (default "0"); for 3.x a
    thinking_level name (default "minimal"). Raises on a value the family
    doesn't accept instead of silently sending the wrong parameter.
    """
    if _is_gemini3(model):
        level = (thinking or "minimal").strip().lower()
        if level not in _GEMINI3_LEVELS:
            raise ValueError(
                f"Gemini 3.x model {model!r} takes thinking_level "
                f"{_GEMINI3_LEVELS}, got {thinking!r} (no zero level exists)"
            )
        from langchain_google_genai import ChatGoogleGenerativeAI

        kw = dict(model=model, temperature=temperature, thinking_level=level)
        if _USE_VERTEX:
            kw.update(
                vertexai=True,
                project=os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"),
                # Gemini 3.x publisher models are not in regional endpoints —
                # us-central1 404s (verified 11/06); they serve from "global".
                location=os.getenv("VERTEX_LOCATION_GEMINI3", "global"),
            )
        return ChatGoogleGenerativeAI(**kw)

    budget = int(thinking) if str(thinking).strip() else 0
    if _USE_VERTEX:
        return ChatVertexAI(
            model=model, temperature=temperature, thinking_budget=budget, **_VERTEX_KW
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model, temperature=temperature, thinking_budget=budget
    )


# Per-node override hook (model experiments): the Ask generation node consumes
# `ask_generation` instead of `flash`, so a model swap is pure config — no
# prompt or node code changes. Unset env → identical to flash (same object).
_ASK_GEN_MODEL = os.getenv("ASK_GENERATION_MODEL", "").strip()
_ASK_GEN_THINKING = os.getenv("ASK_GENERATION_THINKING", "").strip()

ask_generation = (
    build_chat_model(_ASK_GEN_MODEL, temperature=0.1, thinking=_ASK_GEN_THINKING)
    if _ASK_GEN_MODEL
    else flash
)


def extract_text(response) -> str:
    """Extract text content from a Gemini LLM response."""
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()
