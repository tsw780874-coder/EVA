"""Rate Limiter — 基于 Redis 的滑动窗口限流。

用法（FastAPI 依赖）:
    from app.core.rate_limiter import RateLimiter

    limiter = RateLimiter(max_requests=30, window_seconds=60)
    await limiter.check(user_id)  # 超限抛 HTTPException 429
"""

import time
from fastapi import HTTPException, status


class RateLimiter:
    """滑动窗口速率限制器。

    Redis 优先（分布式安全），不可用时回退内存字典（单进程安全）。
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._memory_store: dict[str, list[float]] = {}

    async def check(self, key: str):
        """检查是否超限。超限抛出 HTTPException 429。"""
        now = time.time()
        window_start = now - self.window_seconds

        # 尝试 Redis
        try:
            from app.cache.redis_cache import get_redis_client
            redis = await get_redis_client()
            if redis:
                redis_key = f"ratelimit:{key}"
                # 移除过期条目 + 添加当前请求
                await redis.zremrangebyscore(redis_key, 0, window_start)
                count = await redis.zcard(redis_key)
                if count >= self.max_requests:
                    ttl = await redis.ttl(redis_key)
                    retry_after = max(1, ttl if ttl > 0 else self.window_seconds)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"请求过于频繁，请 {retry_after} 秒后重试",
                        headers={"Retry-After": str(retry_after)},
                    )
                # 记录本次请求
                await redis.zadd(redis_key, {str(now): now})
                await redis.expire(redis_key, self.window_seconds * 2)
                return
        except HTTPException:
            raise
        except Exception:
            pass  # Redis 不可用 → 回退内存

        # 内存回退
        if key not in self._memory_store:
            self._memory_store[key] = []
        timestamps = self._memory_store[key]
        # 清理过期
        self._memory_store[key] = [t for t in timestamps if t > window_start]
        timestamps = self._memory_store[key]

        if len(timestamps) >= self.max_requests:
            oldest = min(timestamps)
            retry_after = max(1, int(oldest + self.window_seconds - now + 1))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请 {retry_after} 秒后重试",
                headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)


# 默认实例
default_limiter = RateLimiter(max_requests=30, window_seconds=60)
