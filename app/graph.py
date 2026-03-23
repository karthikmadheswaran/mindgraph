from langgraph.graph import StateGraph, START, END
from app.nodes.dedup import dedup
from app.nodes.title_summary import title_summary
from app.nodes.deadline import extract_deadlines
from app.state import JournalState
from app.nodes.classify import classify
from app.nodes.extract_entities import extract_entities
from app.nodes.normalize import normalize
from app.nodes.store import store_node

def dedup_router(state: JournalState):
    if state.get("dedup_check_result") == "duplicate":
        return END
    return ["title_summary", "classify", "entities", "deadline"]

def build_graph():
    builder = StateGraph(JournalState)

    builder.add_node("normalize",normalize)
    builder.add_node("dedup",dedup)
    builder.add_node("classify",classify)
    builder.add_node("entities",extract_entities)
    builder.add_node("deadline",extract_deadlines)
    builder.add_node("title_summary",title_summary)
    builder.add_node("store",store_node)


    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "dedup")

    builder.add_conditional_edges("dedup",dedup_router)

    builder.add_edge(["title_summary", "classify", "entities", "deadline"], "store")
    builder.add_edge("store", END)

    workflow = builder.compile()
    return workflow


