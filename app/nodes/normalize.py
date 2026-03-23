# app/nodes/normalize.py
from app.state import JournalState
from datetime import datetime
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")
model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.1)

def extract_text_from_response(response):
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()

async def normalize(state: JournalState) -> dict:
    text = state['raw_text']
    today = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f'''You are a text normalization engine.

1. Clean up typos, slang, and shorthand.
2. Replace ALL relative dates with absolute dates in YYYY-MM-DD format.
   Today's date is {today}.
   Examples: "tomorrow" → the next day's date, "next monday" → the actual date, "by friday" → the actual date, "last tuesday" → the actual date.
3. Preserve original meaning completely.
4. Do NOT summarize or shorten the text.
5. Do NOT add new content or opinions.
6. Return ONLY the cleaned text, nothing else.

Original Text:

{text}
'''
    
    response = await model.ainvoke(prompt)
    cleaned = extract_text_from_response(response)
    
    return {"cleaned_text": cleaned}