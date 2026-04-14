import asyncio
from app.embeddings import get_embedding

async def test():
    text = "Met Rahul at Google office to discuss ProjectX"
    embedding = await get_embedding(text)
    print(f"Text: {text}")
    print(f"Dimensions: {len(embedding)}")
    print(f"First 5 values: {embedding[:5]}")

asyncio.run(test())