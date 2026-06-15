from app.ask_memory import build_ask_prompt
from app.llm import ask_generation, extract_text
from app.services.ask_pipeline.state import AskState
from app.services.observability import langfuse_config


async def generation(state: AskState) -> dict:
    prompt = build_ask_prompt(
        question=state["question"],
        user_memory=state.get("long_term_memory") or "",
        conversation_history=state.get("conversation_history") or "",
        context_text=state.get("assembled_context") or "",
        today_str=state.get("today_str") or "",
        is_low_confidence=bool(state.get("is_low_confidence")),
        is_reask=bool(state.get("is_reask")),
    )
    # ask_generation == flash unless ASK_GENERATION_MODEL/_THINKING env vars
    # override it (model experiments swap the model here, never the prompt).
    response = await ask_generation.ainvoke(prompt, config=langfuse_config())
    return {"answer": extract_text(response)}
