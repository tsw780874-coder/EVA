import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    messages: Annotated[list[dict], operator.add]
    user_query: str
    user_id: str
    intent: str
    search_results: list[dict]
    search_attempted: bool
    price_analysis: dict
    review_summary: dict
    decision: dict
    final_report: str
    next_agent: str
    error: str
