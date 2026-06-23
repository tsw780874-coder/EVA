"""EVA Agent Package — v8 Hybrid AI + Verification + Tool System.

Architecture:
  Request → Intent Router → Parallel Retrieval (RAG + Tools + Web + DB + Memory)
  → Fusion (Rerank + Conflict Resolve) → Verification Gate (mandatory)
  → LLM Synthesis → Streaming Response

Key modules:
  - pipeline: Main 7-layer shopping pipeline (entry point)
  - intent_router: V2.0 8-type intent classification
  - query_rewriter: Query expansion, brand aliases, model abbreviation resolution
  - llm_utils: LLM call utilities (parallel racing, Function Calling, caching)
  - model_router: Dynamic model routing based on query complexity
  - product_alias_db: Product entity resolution (NER) — unified brand/model/category DB
  - product_db: Unified product database (merged hot_products + product_cache)
  - product_graph: Product knowledge graph (brand/series/model hierarchy)
  - product_validator: Cross-category validation
  - live_search: Real-time e-commerce platform search
  - similar_search: Progressive query degradation for fallback
  - product_templates: Template matching for instant responses
  - trending_searches: Trending keyword database
  - popularity_scorer: Unified post-search re-ranking
  - confidence_tiers: Source confidence tier labeling

New in v8:
  - core/verification_gate: Mandatory evidence verification before output
  - tools/: Structured tool system with Function Calling (8 tools)
  - services/vector_memory: Milvus-backed retrieval memory (L3)
  - services/memory_service: Three-layer memory with anti-pollution filters
  - hybrid/: Multi-source intelligence (Web, Memory, Tool, Reasoning)
"""
