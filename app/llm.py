# app/llm.py
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv(encoding="utf-8-sig")
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

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
