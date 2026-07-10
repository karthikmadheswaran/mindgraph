"""Throwaway: list pro-tier Gemini models visible on the Vertex global endpoint
(one models.list call). Not committed."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google import genai

client = genai.Client(
    vertexai=True,
    project=os.getenv("VERTEX_PROJECT", "psychic-surf-498910-f7"),
    location="global",
)
names = []
for m in client.models.list():
    n = getattr(m, "name", "") or ""
    if "gemini" in n:
        names.append(n)
pro = sorted(n for n in names if "pro" in n)
print("PRO-TIER:")
for n in pro:
    print(" ", n)
print("\nALL GEMINI (count):", len(names))
