"""Compatibility stub — the agent no longer uses LangGraph.

v3 replaced the StateGraph with a direct async pipeline (pipeline.py).
This module exists only so old import paths don't break.
"""

from app.agent.state import AgentState


def build_agent_graph():
    """Deprecated — kept for backwards compatibility."""
    raise RuntimeError(
        "agent_app has been replaced by pipeline.run_pipeline(). "
        "Import from app.agent.pipeline instead."
    )


# Old code imports this; provide a dummy that fails early if used.
agent_app = None
