from langgraph.graph import END, START, StateGraph

from app.services.ask_pipeline.context_assembler import context_assembler
from app.services.ask_pipeline.dashboard_context import dashboard_context
from app.services.ask_pipeline.generation import generation
from app.services.ask_pipeline.hybrid_rag import hybrid_rag
from app.services.ask_pipeline.query_agent import query_understanding_agent
from app.services.ask_pipeline.recent_summaries import recent_summaries
from app.services.ask_pipeline.router import router_node
from app.services.ask_pipeline.state import AskState
from app.services.ask_pipeline.temporal_retrieval import temporal_retrieval

_RETRIEVAL_NODES = [
    "temporal_retrieval",
    "recent_summaries",
    "hybrid_rag",
    "dashboard_context",
]


def _build_graph():
    builder = StateGraph(AskState)
    builder.add_node("query_agent", query_understanding_agent)
    builder.add_node("router", router_node)
    builder.add_node("temporal_retrieval", temporal_retrieval)
    builder.add_node("recent_summaries", recent_summaries)
    builder.add_node("hybrid_rag", hybrid_rag)
    builder.add_node("dashboard_context", dashboard_context)
    builder.add_node("context_assembler", context_assembler)
    builder.add_node("generation", generation)

    builder.add_edge(START, "query_agent")
    builder.add_edge("query_agent", "router")
    for node in _RETRIEVAL_NODES:
        builder.add_edge("router", node)
    builder.add_edge(_RETRIEVAL_NODES, "context_assembler")
    builder.add_edge("context_assembler", "generation")
    builder.add_edge("generation", END)

    return builder.compile()


ask_pipeline = _build_graph()
