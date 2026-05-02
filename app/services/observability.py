import logging

logger = logging.getLogger(__name__)
_warned_langfuse_callback = False


def langfuse_config(
    trace_id: str | None = None, user_id: str | None = None
) -> dict:
    """Return a LangChain callback config for Langfuse.

    When trace_id is provided the callback is attached to a named trace so that
    the trace can later be fetched by ID for cost tracking.
    """
    global _warned_langfuse_callback

    try:
        from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
    except ModuleNotFoundError as exc:
        if not _warned_langfuse_callback:
            logger.warning("Langfuse LangChain callback unavailable: %s", exc)
            _warned_langfuse_callback = True
        return {}

    if trace_id:
        try:
            from langfuse import Langfuse

            lf = Langfuse()
            trace = lf.trace(id=trace_id, user_id=user_id, name="entry_pipeline")
            return {"callbacks": [trace.get_langchain_handler()]}
        except Exception as exc:
            logger.warning("Langfuse trace creation failed: %s", exc)

    return {"callbacks": [LangfuseCallbackHandler()]}
