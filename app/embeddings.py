# app/embeddings.py
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Mirror app/llm.py's provider toggle. When USE_VERTEX is truthy, embeddings run
# through Vertex AI (Google Cloud billing) using the SAME gemini-embedding-001 model
# and 1536-dim output, so the vector space is unchanged. Default keeps the AI Studio
# (API-key) path.
_USE_VERTEX = os.getenv("USE_VERTEX", "").strip().lower() in ("1", "true", "yes")

if _USE_VERTEX:
    # Materialize the service-account key into ADC before building the Vertex client
    # (no-op locally; see app/gcp_credentials.py). Must run before genai.Client below.
    from app.gcp_credentials import ensure_adc

    ensure_adc()

    client = genai.Client(
        vertexai=True,
        project=os.getenv("VERTEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("VERTEX_LOCATION", "us-central1"),
    )
else:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def get_embedding(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[float]:
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config={
            "output_dimensionality": 1536,
            "task_type": task_type,
        },
    )
    return result.embeddings[0].values
