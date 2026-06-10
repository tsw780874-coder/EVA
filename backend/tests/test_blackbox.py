"""EVA Black-Box Testing — API endpoints from external perspective.

Tests all public endpoints for:
- Correct HTTP status codes
- Proper response format
- Authentication requirements
- Edge cases (empty input, long input, special chars)
- Error handling
- Streaming SSE events
"""

import httpx
import json
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0
ERRORS = 0


def log(level, msg):
    icon = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️", "SKIP": "⏭️"}.get(level, "•")
    print(f"  {icon} {msg}")


async def api(method, path, json_body=None, headers=None, expected_status=200):
    global PASS, FAIL, ERRORS
    async with httpx.AsyncClient(timeout=15.0) as c:
        try:
            r = await c.request(method, f"{BASE}{path}", json=json_body, headers=headers or {})
            if r.status_code == expected_status:
                PASS += 1
                return r
            else:
                FAIL += 1
                log("FAIL", f"{method} {path} → {r.status_code} (expected {expected_status}) body={r.text[:100]}")
                return r
        except Exception as e:
            ERRORS += 1
            log("FAIL", f"{method} {path} → ERROR: {e}")
            return None


async def stream(path, json_body, headers):
    global PASS, FAIL, ERRORS
    events = []
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            async with c.stream("POST", f"{BASE}{path}", json=json_body, headers=headers) as r:
                if r.status_code != 200:
                    FAIL += 1
                    log("FAIL", f"STREAM {path} → {r.status_code}")
                    return []
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))
            PASS += 1
            return events
        except Exception as e:
            ERRORS += 1
            log("FAIL", f"STREAM {path} → ERROR: {e}")
            return []


async def main():
    global PASS, FAIL, ERRORS
    print("=" * 70)
    print("EVA BLACK-BOX TEST SUITE")
    print("=" * 70)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. HEALTH CHECK (no auth required)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 1. Health Check ──")
    r = await api("GET", "/health")
    if r:
        data = r.json()
        assert data.get("status") == "ok", f"health status: {data}"
        assert data.get("app") == "EVA API", f"app name: {data}"
        log("PASS", "Health check returns correct response")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. AUTH ENDPOINTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 2. Auth Endpoints ──")

    # 2a. Register new user
    test_email = f"test-{int(__import__('time').time())}@eva.com"
    r = await api("POST", "/api/v1/auth/register", {
        "email": test_email, "password": "Test123456", "name": "Test User"
    }, expected_status=201)
    token = None
    if r and r.status_code == 201:
        token = r.json().get("access_token")
        log("PASS", f"Register → 201 + token={'OK' if token else 'MISSING'}")

    # 2b. Register duplicate
    r2 = await api("POST", "/api/v1/auth/register", {
        "email": test_email, "password": "Test123456", "name": "Test User"
    }, expected_status=400)
    if r2 and r2.status_code == 400:
        log("PASS", "Duplicate register → 400 (correctly rejected)")

    # 2c. Login with correct credentials
    r = await api("POST", "/api/v1/auth/login", {
        "email": "admin@eva.com", "password": "admin123"
    })
    if r and r.status_code == 200:
        data = r.json()
        assert data.get("access_token"), "Missing access_token"
        assert data.get("refresh_token"), "Missing refresh_token"
        assert data.get("user", {}).get("email") == "admin@eva.com"
        token = data["access_token"]
        refresh = data["refresh_token"]
        log("PASS", "Login → 200 + tokens + user")

    # 2d. Login with wrong password
    r = await api("POST", "/api/v1/auth/login", {
        "email": "admin@eva.com", "password": "wrongpassword"
    }, expected_status=401)
    if r and r.status_code == 401:
        log("PASS", "Wrong password → 401")

    # 2e. Login with non-existent user
    r = await api("POST", "/api/v1/auth/login", {
        "email": "nonexistent@eva.com", "password": "pass123"
    }, expected_status=401)
    if r and r.status_code == 401:
        log("PASS", "Non-existent user → 401")

    # 2f. Refresh token
    if refresh:
        r = await api("POST", "/api/v1/auth/refresh", headers={
            "Authorization": f"Bearer {refresh}"
        })
        if r and r.status_code == 200:
            new_token = r.json().get("access_token")
            if new_token:
                token = new_token
                log("PASS", "Refresh token → 200 + new access_token")

    # 2g. Empty email login
    r = await api("POST", "/api/v1/auth/login", {
        "email": "", "password": "pass123"
    }, expected_status=422)
    if r and r.status_code == 422:
        log("PASS", "Empty email → 422 (validation)")

    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. UNAUTHENTICATED ACCESS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 3. Auth Guards ──")
    protected = [
        ("GET", "/api/v1/chat/sessions"),
        ("POST", "/api/v1/chat/sessions"),
        ("GET", "/api/v1/products/search"),
        ("GET", "/api/v1/favorites"),
        ("GET", "/api/v1/reports"),
        ("GET", "/api/v1/profile"),
        ("GET", "/api/v1/memory"),
    ]
    for method, path in protected:
        r = await api(method, path, expected_status=401)
        if r and r.status_code == 401:
            log("PASS", f"Protected {path} → 401 (no auth)")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. CHAT SESSIONS (authenticated)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 4. Chat Sessions ──")

    # 4a. List sessions
    r = await api("GET", "/api/v1/chat/sessions", headers=auth_headers)
    session_id = None
    if r:
        sessions = r.json()
        assert isinstance(sessions, list), "Sessions should be a list"
        log("PASS", f"List sessions → 200 ({len(sessions)} sessions)")

    # 4b. Create session
    r = await api("POST", "/api/v1/chat/sessions", {"title": "Test Session"}, headers=auth_headers, expected_status=201)
    if r:
        data = r.json()
        session_id = data.get("id")
        assert session_id, "Missing session id"
        assert data.get("title") == "Test Session"
        log("PASS", f"Create session → 201 (id={session_id[:8]}...)")

    # 4c. Create session with empty title
    r = await api("POST", "/api/v1/chat/sessions", {"title": ""}, headers=auth_headers, expected_status=201)
    if r and r.status_code == 201:
        log("PASS", "Empty title → 201 (uses default)")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. CHAT STREAMING (authenticated)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 5. Chat Streaming ──")

    if session_id and token:
        # 5a. Normal chat
        events = await stream(f"/api/v1/chat/sessions/{session_id}/stream",
                              {"content": "你好"}, auth_headers)
        event_types = [e.get("type") for e in events]
        log("PASS" if "agent_start" in event_types else "FAIL",
            f"Stream '你好' → {len(events)} events, types={set(event_types)}")

        # 5b. Shopping query
        if len(events) > 0:
            # Create new session for shopping test
            r = await api("POST", "/api/v1/chat/sessions", {"title": "Shopping Test"},
                          headers=auth_headers, expected_status=201)
            if r:
                shop_sid = r.json()["id"]
                events2 = await stream(f"/api/v1/chat/sessions/{shop_sid}/stream",
                                       {"content": "iPhone 16 Pro Max价格"}, auth_headers)
                types2 = [e.get("type") for e in events2]
                log("PASS" if "agent_result" in types2 else "FAIL",
                    f"Stream shopping → {len(events2)} events, types={set(types2)}")

                # 5c. Check trust metadata
                trust_events = [e for e in events2 if e.get("type") == "trust"]
                if trust_events:
                    t = trust_events[0]
                    log("PASS", f"Trust metadata: conf={t.get('confidence')} src={t.get('data_source')}")
                else:
                    log("FAIL", "No trust metadata in shopping response")

        # 5d. Empty content
        r = await api("POST", f"/api/v1/chat/sessions/{session_id}/stream",
                      {"content": ""}, headers=auth_headers, expected_status=422)
        if r and r.status_code == 422:
            log("PASS", "Empty content → 422 (validation)")

        # 5e. Long query
        long_q = "请详细对比分析iPhone、华为、小米三款旗舰手机的性价比、拍照、续航、屏幕、系统体验等各个方面，给出购买建议。" * 3
        r = await api("POST", "/api/v1/chat/sessions", {"title": "Long Query"},
                      headers=auth_headers, expected_status=201)
        if r:
            long_sid = r.json()["id"]
            events3 = await stream(f"/api/v1/chat/sessions/{long_sid}/stream",
                                    {"content": long_q}, auth_headers)
            log("PASS", f"Long query ({len(long_q)} chars) → {len(events3)} events")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. PRODUCTS API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 6. Products API ──")
    r = await api("GET", "/api/v1/products/search?q=iPhone", headers=auth_headers)
    if r:
        products = r.json()
        assert isinstance(products, list), "Products should be a list"
        log("PASS", f"Search 'iPhone' → {len(products)} products")

    r = await api("GET", "/api/v1/products/search?q=", headers=auth_headers)
    if r:
        log("PASS", f"Empty search → 200 ({len(r.json())} products)")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. FAVORITES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 7. Favorites ──")
    r = await api("GET", "/api/v1/favorites", headers=auth_headers)
    if r:
        favs = r.json()
        log("PASS", f"List favorites → 200 ({len(favs) if isinstance(favs, list) else 'obj'})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 8. REPORTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 8. Reports ──")
    r = await api("GET", "/api/v1/reports", headers=auth_headers)
    if r:
        reports = r.json()
        log("PASS", f"List reports → 200 ({len(reports) if isinstance(reports, list) else 'obj'})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 9. PROFILE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 9. Profile ──")
    r = await api("GET", "/api/v1/profile", headers=auth_headers)
    if r:
        profile = r.json()
        log("PASS", f"Profile → 200 (email={profile.get('email','?')})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 10. MEMORY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 10. Memory ──")
    r = await api("GET", "/api/v1/memory", headers=auth_headers)
    if r:
        mem = r.json()
        log("PASS", f"Memory → 200 ({len(mem) if isinstance(mem, list) else 'obj'})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 11. MODELS (public endpoint)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 11. Models ──")
    r = await api("GET", "/api/v1/models", headers=auth_headers)
    if r:
        models = r.json()
        log("PASS", f"Models → 200 ({len(models) if isinstance(models, list) else 'obj'})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 12. EDGE CASES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n── 12. Edge Cases ──")

    # 12a. SQL injection attempt
    r = await api("GET", "/api/v1/products/search?q='; DROP TABLE users; --", headers=auth_headers)
    log("PASS" if r and r.status_code == 200 else "FAIL", "SQL injection → handled safely")

    # 12b. XSS attempt
    r = await api("POST", "/api/v1/auth/login", {
        "email": "<script>alert('xss')</script>", "password": "test"
    }, expected_status=422)
    log("PASS" if r and r.status_code == 422 else "FAIL", "XSS in login → 422 (validation)")

    # 12c. Invalid JSON body
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/api/v1/auth/login",
                         content="not json", headers={"Content-Type": "application/json"})
        log("PASS" if r.status_code in (400, 422) else "FAIL", f"Invalid JSON → {r.status_code}")

    # 12d. Wrong HTTP method
    r = await api("POST", "/health", expected_status=405)
    log("PASS" if r and r.status_code == 405 else "FAIL", "POST /health → 405")

    # 12e. Non-existent endpoint
    r = await api("GET", "/api/v1/nonexistent", headers=auth_headers, expected_status=404)
    log("PASS" if r and r.status_code == 404 else "FAIL", "Non-existent endpoint → 404")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SUMMARY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    total = PASS + FAIL + ERRORS
    print("\n" + "=" * 70)
    print(f"BLACK-BOX TEST RESULTS:")
    print(f"  ✅ PASS:  {PASS}")
    print(f"  ❌ FAIL:  {FAIL}")
    print(f"  ⚠️  ERROR: {ERRORS}")
    print(f"  📊 TOTAL: {total}")
    rate = (PASS / total * 100) if total > 0 else 0
    print(f"  📈 Pass Rate: {rate:.1f}%")
    print("=" * 70)

    return FAIL == 0 and ERRORS == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
