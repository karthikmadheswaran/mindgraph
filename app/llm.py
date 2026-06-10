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
    # NOTE: thinking_budget is a Gemini-Developer-API (AI Studio) kwarg and is NOT
    # passed to ChatVertexAI; flash-lite on Vertex uses its default thinking config.
    flash = ChatVertexAI(model="gemini-2.5-flash-lite", temperature=0.1, **_VERTEX_KW)
    flash_creative = ChatVertexAI(model="gemini-2.5-flash-lite", temperature=0.3, **_VERTEX_KW)
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


def extract_text(response) -> str:
    """Extract text content from a Gemini LLM response."""
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()
