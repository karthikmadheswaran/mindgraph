# app/llm.py
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

# Pipeline nodes use flash (fast, cheap).
flash = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.1)

# Ask endpoint query rewriting uses flash with slightly higher temperature.
flash_creative = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.3)

# Insight engine uses pro for deeper reasoning.
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
