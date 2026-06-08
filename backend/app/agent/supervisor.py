"""Supervisor stub — kept for backwards compatibility with imports.

The supervisor node has been removed from the graph (v2 optimisation).
Routing is now handled by deterministic conditional edges directly
between agent nodes, eliminating 5 graph round-trips from the shopping
flow.  See graph.py for the new linear pipeline structure.
"""

from app.agent.state import AgentState


async def supervisor_node(state: AgentState) -> dict:
    """Deprecated — the graph no longer uses a central supervisor.

    This function exists only so that old import paths don't break.
    """
    return {"next_agent": "__end__"}
