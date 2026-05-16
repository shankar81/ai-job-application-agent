"""LangGraph application entry point.

Wires nodes into the StateGraph and exposes:
  app               — compiled graph, used by scraper/jobs.py and scraper/easy_apply.py
  checkpoint_config — shared thread config for InMemorySaver
"""

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agentic.nodes import (
    create_candidate_profile,
    fill_form,
    init,
    match_jobs,
    should_create_profile,
)
from agentic.state import AgentState

load_dotenv()

# ---------------------------------------------------------------------------
# Checkpoint config (shared across all Easy Apply steps in a single run)
# ---------------------------------------------------------------------------

checkpoint_config = {
    "configurable": {
        "thread_id": "linkedin-apply-1",
    }
}

# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

graph = StateGraph(AgentState)

graph.add_node("init", init)
graph.add_node("create_profile", create_candidate_profile)
graph.add_node("match_jobs", match_jobs)
graph.add_node("fill_form", fill_form)

graph.add_edge(START, "init")

graph.add_conditional_edges(
    "init",
    should_create_profile,
    {
        "create_profile": "create_profile",
        "match_jobs": "match_jobs",
        "fill_form": "fill_form",
        "exit": END,
    },
)

graph.add_edge("create_profile", "match_jobs")
graph.add_edge("match_jobs", END)
graph.add_edge("fill_form", END)

checkpointer = InMemorySaver()
app = graph.compile(checkpointer=checkpointer)
