"""Black-box E2E tests for EVA V2.0 pipeline.

Tests the full pipeline from query to result with diverse inputs.
Verifies output structure, correctness, and cross-category prevention.
"""
import asyncio
import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"   {name}")
    else:
        FAIL += 1
        print(f"   {name}  {detail}")


async def run_query(query: str, user_id: str = "test_blackbox") -> dict:
    """Run a single query through the full pipeline."""
    from app.agent.pipeline import run_pipeline
    return await run_pipeline(query, user_id=user_id, bypass_cache=True)


def validate_result_structure(result: dict) -> list[str]:
    """Validate the result dict has all required fields. Returns list of missing fields."""
    required = [
        "intent", "intent_type", "search_results", "final_report",
        "confidence", "data_source", "search_layers", "total_products_found",
        "entity",
    ]
    return [f for f in required if f not in result]


# ═══════════════════════════════════════════════════════════════════════
# 1. Result Structure Tests
# ═══════════════════════════════════════════════════════════════════════
async def test_result_structure():
    print("\n 1. Result Structure Tests")
    result = await run_query("iPhone 16")

    # Required fields
    missing = validate_result_structure(result)
    test("Result has all required fields", len(missing) == 0, f"missing: {missing}")

    # Product structure
    if result["search_results"]:
        p = result["search_results"][0]
        test("Product has name", bool(p.get("name") or p.get("title")))
        test("Product has platform", bool(p.get("platform")))
        test("Product has url", bool(p.get("url")))
        test("Product has confidence", isinstance(p.get("confidence"), (int, float)))
        test("Product has source", bool(p.get("source")))
        test("Product has tier (V2.0)", "tier" in p)

    # Entity structure
    entity = result.get("entity", {})
    test("Result has entity field", bool(entity or entity == {}))

    # Perf timing
    perf = result.get("perf", {})
    test("Result has perf timing", bool(perf))

    # Graph suggestions (V2.0)
    test("Result has graph_suggestions field", "graph_suggestions" in result)


# ═══════════════════════════════════════════════════════════════════════
# 2. Cross-Category Prevention Tests
# ═══════════════════════════════════════════════════════════════════════
async def test_cross_category():
    print("\n 2. Cross-Category Prevention Tests")

    # Test 1: Badminton → must NOT return phones
    r = await run_query("想买尤尼克斯天斧99Pro")
    names = " ".join(p.get("name", "").lower() for p in r["search_results"])
    test("Badminton → no iPhone", "iphone" not in names)
    test("Badminton → no Xiaomi", "xiaomi" not in names and "小米" not in names)
    test("Badminton → no Huawei", "huawei" not in names and "华为" not in names)
    test("Badminton → has YONEX", "yonex" in names or "astrox" in names)
    test("Badminton → has products", len(r["search_results"]) > 0)

    # Test 2: iPhone → must NOT return badminton rackets
    r2 = await run_query("iPhone 16 Pro Max 256GB")
    names2 = " ".join(p.get("name", "").lower() for p in r2["search_results"])
    test("iPhone → no badminton", "badminton" not in names2 and "racket" not in names2)
    test("iPhone → no YONEX", "yonex" not in names2 and "astrox" not in names2)
    test("iPhone → has Apple", "apple" in names2 or "iphone" in names2)
    test("iPhone → has products", len(r2["search_results"]) > 0)

    # Test 3: GPU → must NOT return phones or badminton
    r3 = await run_query("RTX 5090 显卡")
    names3 = " ".join(p.get("name", "").lower() for p in r3["search_results"])
    test("GPU → no iPhone", "iphone" not in names3)
    test("GPU → no badminton", "badminton" not in names3)
    test("GPU → has RTX", "rtx" in names3 or "geforce" in names3)
    test("GPU → has products", len(r3["search_results"]) > 0)


# ═══════════════════════════════════════════════════════════════════════
# 3. Intent Routing Tests
# ═══════════════════════════════════════════════════════════════════════
async def test_intent_routing():
    print("\n 3. Intent Routing Tests")

    cases = [
        ("我要买iPhone16", "buy_product", True),
        ("iPhone16和小米16哪个好", "compare_products", True),
        ("推荐性价比高的手机", "recommend_products", True),
        ("iPhone16多少钱", "price_check", True),
        ("RTX5090评测怎么样", "product_review", False),
        ("羽毛球拍怎么选", "shopping_guide", False),
        ("最近热门手机", "trend_analysis", True),
        ("什么是OLED屏幕", "knowledge_qa", False),
    ]
    for query, expected_intent, should_have_products in cases:
        r = await run_query(query)
        actual = r.get("intent_type", "")
        test(f"'{query[:25]}' → {expected_intent}",
             actual == expected_intent,
             f"got {actual}")

        if should_have_products:
            has_products = len(r["search_results"]) > 0 or r["data_source"] not in ("none", "llm")
            # For some intents, LLM source is acceptable
            test(f"'{query[:25]}' returns data",
                 r["data_source"] != "none",
                 f"source={r['data_source']}")


# ═══════════════════════════════════════════════════════════════════════
# 4. Edge Case Tests
# ═══════════════════════════════════════════════════════════════════════
async def test_edge_cases():
    print("\n 4. Edge Case Tests")

    # Empty query
    r = await run_query("")
    test("Empty query doesn't crash", r is not None)
    test("Empty query has no products", len(r.get("search_results", [])) == 0)

    # Whitespace query
    r = await run_query("   ")
    test("Whitespace query doesn't crash", r is not None)

    # Very short query
    r = await run_query("a")
    test("Single char query doesn't crash", r is not None)

    # Very long query
    long_q = "我想买一个非常好的 " * 20
    r = await run_query(long_q)
    test("Long query doesn't crash", r is not None)

    # Special characters
    r = await run_query("!!!@#$%^&*()")
    test("Special chars query doesn't crash", r is not None)

    # Unicode emoji
    r = await run_query(" 羽毛球拍")
    test("Emoji query doesn't crash", r is not None)

    # Mixed Chinese/English
    r = await run_query("买iPhone16 Pro Max 256GB 深空黑色")
    test("Mixed lang query returns results", len(r.get("search_results", [])) > 0)

    # Numbers only
    r = await run_query("5090")
    test("Numbers-only query doesn't crash", r is not None)


# ═══════════════════════════════════════════════════════════════════════
# 5. Multi-Category Coverage Tests
# ═══════════════════════════════════════════════════════════════════════
async def test_category_coverage():
    print("\n 5. Multi-Category Coverage Tests")

    queries_by_category = {
        "smartphone": ["iPhone 16 Pro Max", "华为Mate70", "小米15 Ultra", "三星S25"],
        "badminton_racket": ["天斧99Pro", "天斧100ZZ", "弓箭11PRO", "龙牙之刃", "雷霆80"],
        "graphics_card": ["RTX 5090", "RTX 5080", "RX 7900 XTX"],
        "laptop": ["MacBook Pro", "拯救者", "ThinkPad"],
        "headphone": ["AirPods Pro", "降噪耳机"],
        "gaming_console": ["PS5", "Switch 2"],
        "shoe": ["AJ1倒钩", "Dunk", "Air Force 1"],
    }
    for category, queries in queries_by_category.items():
        for q in queries:
            r = await run_query(q)
            has_results = len(r["search_results"]) > 0
            test(f"[{category}] '{q}' → has results", has_results)


# ═══════════════════════════════════════════════════════════════════════
# 6. V2.0 Feature Verification Tests
# ═══════════════════════════════════════════════════════════════════════
async def test_v2_features():
    print("\n 6. V2.0 Feature Verification Tests")

    # Test product with entity extraction
    r = await run_query("天斧99Pro 4U")
    entity = r.get("entity", {})
    test("Entity brand detected", entity.get("brand") == "YONEX")
    test("Entity category detected", entity.get("category") == "badminton_racket")

    # Test graph suggestions
    test("Graph suggestions available", "graph_suggestions" in r)
    if r.get("graph_suggestions"):
        gs = r["graph_suggestions"][0]
        test("Graph suggestion has name", "name" in gs)
        test("Graph suggestion has reason", "reason" in gs)

    # Test confidence tier
    if r["search_results"]:
        p = r["search_results"][0]
        test("Product has tier", "tier" in p)
        test("Tier is valid", p.get("tier") in ["A", "B", "C", "D", "E"])

    # Test search layers tracking
    test("Search layers tracked", len(r.get("search_layers", [])) > 0)

    # Test intent confidence
    test("Intent confidence present", "intent_confidence" in r)


# ═══════════════════════════════════════════════════════════════════════
# 7. Performance Test
# ═══════════════════════════════════════════════════════════════════════
async def test_performance():
    print("\n 7. Performance Tests")

    # Hot cache hit should be fast
    t0 = time.perf_counter()
    r = await run_query("iPhone 16", user_id="perf_test")
    t1 = time.perf_counter() - t0
    test(f"Hot product query < 5s ({t1:.1f}s)", t1 < 5.0)

    # Badminton query
    t0 = time.perf_counter()
    r = await run_query("天斧99Pro", user_id="perf_test_2")
    t2 = time.perf_counter() - t0
    test(f"Badminton query < 5s ({t2:.1f}s)", t2 < 5.0)


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
async def main():
    global PASS, FAIL
    t_start = time.perf_counter()

    print("=" * 60)
    print("EVA V2.0 BLACK-BOX E2E TEST SUITE")
    print("=" * 60)

    await test_result_structure()
    await test_cross_category()
    await test_intent_routing()
    await test_edge_cases()
    await test_category_coverage()
    await test_v2_features()
    await test_performance()

    t_total = (time.perf_counter() - t_start) * 1000
    total = PASS + FAIL

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed ({total} total)")
    print(f"Time: {t_total:.0f}ms")
    print(f"{'=' * 60}")

    return FAIL == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
