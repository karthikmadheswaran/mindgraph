from app.services.ask_pipeline.state import AskState


async def router_node(state: AskState) -> dict:
    """Passthrough fan-out anchor. Routing flags already live on state."""
    return {}
