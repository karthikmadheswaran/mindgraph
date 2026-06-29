from langgraph.graph import StateGraph, START, END
from app.nodes.dedup import dedup
from app.nodes.title_summary import title_summary
from app.nodes.deadline import extract_deadlines
from app.nodes.intentions import extract_intentions
from app.state import JournalState
from app.nodes.classify import classify
from app.nodes.extract_entities import extract_entities
from app.nodes.extract_relations import extract_relations
from app.nodes.normalize import normalize
from app.nodes.store import store_node
from app.nodes.compute_discoveries import compute_discoveries
from app.nodes.assemble_dispatch import assemble_dispatch


def dedup_router(state: JournalState):
    if state.get("dedup_check_result") == "duplicate":
        return END
    return ["title_summary", "classify", "entities", "deadline", "intentions"]


def build_graph():
    builder = StateGraph(JournalState)

    builder.add_node("normalize", normalize)
    builder.add_node("dedup", dedup)
    builder.add_node("classify", classify)
    builder.add_node("entities", extract_entities)
    builder.add_node("deadline", extract_deadlines)
    builder.add_node("intentions", extract_intentions)
    builder.add_node("title_summary", title_summary)
    builder.add_node("extract_relations", extract_relations)
    builder.add_node("compute_discoveries", compute_discoveries)
    builder.add_node("store", store_node)
    builder.add_node("assemble_dispatch", assemble_dispatch)

    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "dedup")

    # dedup fans out to all 5 extraction nodes in parallel (or routes to END on duplicate)
    builder.add_conditional_edges("dedup", dedup_router)

    # All 5 extraction nodes fan in; then fan OUT to extract_relations AND compute_discoveries in parallel
    builder.add_edge(
        ["title_summary", "classify", "entities", "deadline", "intentions"],
        "extract_relations",
    )
    builder.add_edge(
        ["title_summary", "classify", "entities", "deadline", "intentions"],
        "compute_discoveries",
    )

    # Both extract_relations and compute_discoveries fan in to store
    builder.add_edge(["extract_relations", "compute_discoveries"], "store")

    builder.add_edge("store", "assemble_dispatch")
    builder.add_edge("assemble_dispatch", END)

    workflow = builder.compile()
    return workflow
