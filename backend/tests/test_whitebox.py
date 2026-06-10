"""EVA White-Box Testing — internal module logic verification.

Tests all internal modules with knowledge of their implementation:
- Intent classification accuracy
- Model router correctness
- Data verifier logic
- Confidence scoring math
- Citation tracking
- RAG product content parsing
- Template matching
- Pipeline flow paths
- Prompt anti-hallucination checks
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label} — {detail}")


def check_eq(label, actual, expected):
    ok = actual == expected
    check(label, ok, f"got={actual} expected={expected}")
    return ok


def check_contains(label, haystack, needle):
    ok = needle in haystack
    check(label, ok, f"'{needle}' not found in '{str(haystack)[:80]}'")
    return ok


def check_not_contains(label, haystack, needle):
    ok = needle not in haystack
    check(label, ok, f"'{needle}' SHOULD NOT be in '{str(haystack)[:80]}'")
    return ok


def main():
    global PASS, FAIL
    print("=" * 70)
    print("EVA WHITE-BOX TEST SUITE")
    print("=" * 70)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. INTENT CLASSIFICATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 1. Intent Classification ──")
    from app.agent.pipeline import classify_intent

    # Shopping intent
    for q in ["iPhone价格", "对比华为小米", "耳机推荐", "买笔记本", "最便宜手机",
              "折扣", "促销", "哪里买", "多少钱", "性价比高"]:
        check_eq(f"shopping: '{q}'", classify_intent(q), "shopping")

    # Complaint intent
    for q in ["投诉京东", "退款申请", "假货举报", "差评", "质量问题退货"]:
        check_eq(f"complaint: '{q}'", classify_intent(q), "complaint")

    # Product query intent
    for q in ["iPhone参数", "配置规格", "处理器型号", "芯片性能", "续航时间"]:
        check_eq(f"product_query: '{q}'", classify_intent(q), "product_query")

    # General intent
    for q in ["你好", "天气怎么样", "hello", "how are you", "今天星期几"]:
        check_eq(f"general: '{q}'", classify_intent(q), "general")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. MODEL ROUTER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 2. Model Router ──")
    from app.agent.model_router import route_query, SIMPLE_PROFILE, SHOPPING_PROFILE, COMPLEX_PROFILE

    # Simple queries should route to Groq
    r = route_query("你好")
    check("greeting → simple", r.description == "simple_chat",
          f"got {r.description}")
    check("greeting uses Groq", "groq" in r.providers, f"providers={r.providers}")

    r = route_query("Hello!")
    check("english greeting → simple", r.description == "simple_chat",
          f"got {r.description}")

    # Shopping queries → balanced or complex
    r = route_query("iPhone价格", "shopping")
    check("shopping with intent → not simple", r.description != "simple_chat",
          f"got {r.description}")

    # Complex query → complex profile
    r = route_query("详细对比分析iPhone华为小米三款旗舰性价比并给出购买建议", "shopping")
    check("complex → complex_analysis", r.description == "complex_analysis",
          f"got {r.description}")

    # Short shopping query
    r = route_query("耳机推荐", "shopping")
    check("short shopping → simple/balanced", r.description in ("simple_chat", "shopping_search"),
          f"got {r.description}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. CONFIDENCE SCORING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 3. Confidence Scoring ──")
    from app.core.confidence import ConfidenceScorer

    # High confidence
    s = ConfidenceScorer.compute(sources=3, freshness_days=7, relevance=0.9, authority="official")
    check("high conf ≥ 90", s >= 90, f"score={s}")

    # Medium confidence
    s = ConfidenceScorer.compute(sources=1, freshness_days=60, relevance=0.6, authority="database")
    check("medium conf 40-70", 40 <= s <= 70, f"score={s}")

    # Low confidence
    s = ConfidenceScorer.compute(sources=0, freshness_days=None, relevance=0.0, authority="simulated")
    check_eq("simulated → 0", s, 0.0)

    # Formatting
    fmt = ConfidenceScorer.format(95)
    check_contains("high format", fmt, "🟢")
    fmt = ConfidenceScorer.format(50)
    check_contains("low format", fmt, "🟠")
    fmt = ConfidenceScorer.format(0)
    check_contains("zero format", fmt, "🔴")

    # Warnings
    w = ConfidenceScorer.get_warning(0)
    check("zero score → warning", w is not None)
    w = ConfidenceScorer.get_warning(50)
    check("low score → warning", w is not None)
    w = ConfidenceScorer.get_warning(80)
    check("high score → no warning", w is None)

    # Breakdown
    bd = ConfidenceScorer.compute_with_breakdown(sources=2, freshness_days=45, relevance=0.7, authority="api")
    check("breakdown has 4 parts", len(bd.as_dict()) == 4, str(bd.as_dict()))
    check("breakdown total equals sum", abs(bd.total - (bd.sources_score + bd.freshness_score + bd.relevance_score + bd.authority_score)) < 0.1)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. CITATION TRACKER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 4. Citation Tracker ──")
    from app.core.citations import CitationTracker

    t = CitationTracker()
    t.add("iPhone 16 Pro Max 京东价格", source_type="database", source_name="ProductDB")
    t.add("华为Mate 70 Pro 参数", source_type="rag", source_name="知识库")

    block = t.render()
    check_contains("block has db source", block, "ProductDB")
    check_contains("block has rag source", block, "知识库")
    check_contains("block has 信息来源 header", block, "信息来源")

    # Simulated flag
    t2 = CitationTracker()
    t2.mark_simulated()
    check("all_simulated=True", t2.all_simulated, str(t2._has_simulated_data))
    check("has_real_data=False", not t2.has_real_data)
    short = t2.render_short()
    check_contains("short simulated warning", short, "模拟")

    # Real data tracker
    t3 = CitationTracker()
    t3.add("数据来自京东", source_type="database", source_name="JD DB")
    check("has_real_data=True", t3.has_real_data)
    check("all_simulated=False", not t3.all_simulated)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. RAG PRODUCT PARSER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 5. RAG Product Parser ──")
    from app.agent.pipeline import _parse_product_from_content

    # Valid knowledge base content with YAML frontmatter
    content = """---
name: iPhone 16 Pro Max
brand: Apple
category: smartphone
platforms:
  - name: 京东
    price: 8999
    original_price: 9999
specs:
  chip: A18 Pro
  display: 6.9寸 OLED
rating: 4.8
source: Apple Official
source_url: https://www.apple.com.cn/
updated_at: 2026-06-01
---

# iPhone 16 Pro Max

旗舰智能手机。"""

    product = _parse_product_from_content(content, "Apple", 0.85)
    check("parse: name", product is not None and product["name"] == "iPhone 16 Pro Max",
          str(product))
    check("parse: platform", product is not None and "京东" in str(product.get("platform", "")),
          str(product))

    # Empty content
    product = _parse_product_from_content("", "unknown", 0.0)
    check("empty content → None", product is None)

    # Price-only content (fallback regex)
    content2 = "产品名称: AirPods Pro 3\n价格: ¥1799\n来源: Apple"
    product = _parse_product_from_content(content2, "test", 0.5)
    check("fallback parse", product is not None, str(product))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. TEMPLATE MATCHING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 6. Template Matching ──")
    from app.agent.product_templates import match_template

    # Known templates
    for kw in ["iPhone", "华为", "小米", "耳机", "samsung"]:
        result = match_template(kw)
        check(f"template: '{kw}'", result is not None)
        if result:
            products, review = result
            # All should have simulated markers
            for p in products:
                check(f"  '{kw}' → source=simulated", p.get("source") == "simulated",
                      f"source={p.get('source')}")
                check(f"  '{kw}' → confidence=0.0", p.get("confidence") == 0.0,
                      f"conf={p.get('confidence')}")

    # Unknown template
    result = match_template("xyzzy_nonexistent_thing")
    check("unknown template → None", result is None)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. ANTI-HALLUCINATION PROMPT CHECK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 7. Anti-Hallucination Prompts ──")
    from app.agent.pipeline import _RAG_SUMMARIZE_PROMPT, _NO_DATA_PROMPT, _QUICK_CHAT_PROMPT

    # RAG prompt should NOT ask model to generate products
    check_not_contains("RAG prompt no '生成'", _RAG_SUMMARIZE_PROMPT, "生成")
    check_contains("RAG prompt says '只使用'", _RAG_SUMMARIZE_PROMPT, "只使用")
    check_contains("RAG prompt says '知识库'", _RAG_SUMMARIZE_PROMPT, "知识库")

    # No-data prompt should not guess
    check_not_contains("no-data prompt no '生成'", _NO_DATA_PROMPT, "生成")
    check_contains("no-data says '编造'", _NO_DATA_PROMPT, "编造")

    # Quick chat prompt
    check_contains("chat prompt says '凭记忆'", _QUICK_CHAT_PROMPT, "凭记忆")
    check_contains("chat prompt says '知识'", _QUICK_CHAT_PROMPT, "知识")

    # Old hallucination prompt must not exist
    # (check that _COMBINED_PROMPT which had "生成3个商品" is gone)
    import app.agent.pipeline as pipe_mod
    has_old_prompt = hasattr(pipe_mod, '_COMBINED_PROMPT')
    check("old COMBINED_PROMPT removed", not has_old_prompt,
          "v4 prompt with '生成3个商品' still exists!")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 8. VERIFIER FRESHNESS CHECK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 8. Data Verifier ──")
    from app.core.verifier import _check_freshness, FRESH_THRESHOLD_DAYS, STALE_THRESHOLD_DAYS

    # Recent data
    age, stale, warn = _check_freshness("2026-06-09")
    check("recent (1 day): not stale", not stale)
    check("recent: age=1", age == 1, f"age={age}")

    # Old data
    age, stale, warn = _check_freshness("2025-01-01")
    check("old (>1yr): stale", stale, f"age={age}")
    check("old: warning present", warn is not None)

    # No date
    age, stale, warn = _check_freshness(None)
    check("no date: age=None", age is None)
    check("no date: not stale", not stale)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 9. PERF TIMER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 9. Performance Timer ──")
    from app.core.perf import get_timer
    import time

    timer = get_timer()
    timer.start("test_block")
    time.sleep(0.05)
    elapsed = timer.stop("test_block")
    check("timer 50ms", 40 < elapsed < 100, f"elapsed={elapsed}ms")

    timer.start("block2")
    _ = timer.stop("block2")
    report = timer.report()
    check("report has keys", "test_block_ms" in report and "block2_ms" in report,
          str(report))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 10. PIPELINE DECISION COMPUTE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 10. Pipeline Decision Logic ──")
    from app.agent.pipeline import compute_decision, compute_price_analysis

    # Price analysis with real data
    products = [
        {"platform": "京东", "price": 8999, "original_price": 9999},
        {"platform": "天猫", "price": 9199, "original_price": 9999},
        {"platform": "拼多多", "price": 8499, "original_price": 9999},
    ]
    pa = compute_price_analysis(products)
    check_eq("best price platform", pa["best_platform"], "拼多多")
    check("best price value", pa["best_price"] == 8499, str(pa))
    check("price range", "8,499" in pa["price_range"] or "8499" in pa["price_range"],
          pa["price_range"])

    # Decision with high confidence
    d = compute_decision(pa, {"verdict": "值得购买", "pros": ["好", "快"], "cons": ["贵"]}, confidence=85)
    check("high conf → consider", d["recommendation"] == "consider", str(d))

    # Decision with low confidence
    d2 = compute_decision(pa, {}, confidence=50)
    check("low conf → low_confidence", d2["recommendation"] == "low_confidence", str(d2))

    # Decision with no data
    d3 = compute_decision({}, {}, confidence=0)
    check("no data → no_data", d3["recommendation"] == "no_data", str(d3))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SUMMARY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    total = PASS + FAIL
    print("\n" + "=" * 70)
    print(f"WHITE-BOX TEST RESULTS:")
    print(f"  ✅ PASS:  {PASS}")
    print(f"  ❌ FAIL:  {FAIL}")
    print(f"  📊 TOTAL: {total}")
    rate = (PASS / total * 100) if total > 0 else 0
    print(f"  📈 Pass Rate: {rate:.1f}%")
    print("=" * 70)

    return FAIL == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
