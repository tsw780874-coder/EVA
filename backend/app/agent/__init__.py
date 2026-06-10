"""EVA Agent Package — v6 Multi-Layer Search Architecture.

Modules:
  - pipeline: Main 5-layer shopping pipeline (entry point)
  - query_rewriter: Query expansion, brand aliases, model abbreviation resolution
  - live_search: Real-time e-commerce platform search (HTTP scraping + LLM)
  - product_cache: Hot product cache with seed data (100+ products)
  - similar_search: Progressive query degradation for fallback search
  - product_templates: Template matching for instant responses
  - intent: Keyword-based intent classification
  - llm_utils: LLM call utilities with parallel racing
  - model_router: Dynamic model routing based on query complexity
  - state: AgentState definition
  - graph: Deprecated stub (kept for backwards compat)
"""
