import logging

logger = logging.getLogger(__name__)
_warned_langfuse_callback = False


def langfuse_config() -> dict:
    global _warned_langfuse_callback

    try:
        from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
    except ModuleNotFoundError as exc:
        if not _warned_langfuse_callback:
            logger.warning("Langfuse LangChain callback unavailable: %s", exc)
            _warned_langfuse_callback = True
        return {}

    return {"callbacks": [LangfuseCallbackHandler()]}
