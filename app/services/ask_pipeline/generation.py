from app.ask_memory import build_ask_prompt
from app.llm import extract_text, flash
from app.services.ask_pipeline.state import AskState
from app.services.observability import langfuse_config


async def generation(state: AskState) -> dict:
    prompt = build_ask_prompt(
        question=state["question"],
        user_memory=state.get("long_term_memory") or "",
        conversation_history=state.get("conversation_history") or "",
        context_text=state.get("assembled_context") or "",
        today_str=state.get("today_str") or "",
    )
    response = await flash.ainvoke(prompt, config=langfuse_config())
    return {"answer": extract_text(response)}
