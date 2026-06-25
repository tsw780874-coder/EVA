from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "EVA API"
    debug: bool = True

    # Database
    use_sqlite: bool = False
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "eva"
    db_password: str = "eva_secret"
    db_name: str = "eva"
    database_url: str | None = None

    @property
    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.use_sqlite:
            return "sqlite+aiosqlite:///./eva_dev.db"
        return f"mysql+aiomysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # JWT
    jwt_secret: str = "eva-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ============ AI 模型配置 (7个) ============

    # 1. DeepSeek (管理员主力)
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # 2. OpenAI GPT-4o (高精度)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    # 3. 智谱 GLM-4-Flash (免费快速)
    glm_flash_api_key: str = ""
    glm_flash_model: str = "glm-4-flash"
    glm_flash_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # 4. 智谱 GLM-4.7-Flash (最新快速)
    glm47_flash_api_key: str = ""
    glm47_flash_model: str = "glm-4.7-flash"
    glm47_flash_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # 5. 百度 ERNIE-Speed-8K (轻量快速)
    ernie_speed_api_key: str = ""
    ernie_speed_model: str = "ernie-speed-8k"
    ernie_speed_base_url: str = "https://qianfan.baidubce.com/v2"

    # 6. 百度 ERNIE-3.5-8K (标准)
    ernie35_api_key: str = ""
    ernie35_model: str = "ernie-3.5-8k"
    ernie35_base_url: str = "https://qianfan.baidubce.com/v2"

    # 7. 火山引擎 Seedream (图像生成)
    seedream_api_key: str = ""

    # 8. Groq (极速推理 LPU)
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Web Search
    serpapi_key: str = ""
    bing_api_key: str = ""

    # ============ 默认 LLM 提供商 ============
    default_llm_provider: str = "deepseek"

    @property
    def llm_config(self) -> dict:
        """Get config dict for the default LLM provider."""
        providers = {
            "deepseek": {"api_key": self.deepseek_api_key, "base_url": self.deepseek_base_url, "model": self.deepseek_model},
            "openai": {"api_key": self.openai_api_key, "base_url": self.openai_base_url, "model": self.openai_model},
            "glm_flash": {"api_key": self.glm_flash_api_key, "base_url": self.glm_flash_base_url, "model": self.glm_flash_model},
            "glm47_flash": {"api_key": self.glm47_flash_api_key, "base_url": self.glm47_flash_base_url, "model": self.glm47_flash_model},
            "ernie_speed": {"api_key": self.ernie_speed_api_key, "base_url": self.ernie_speed_base_url, "model": self.ernie_speed_model},
            "ernie35": {"api_key": self.ernie35_api_key, "base_url": self.ernie35_base_url, "model": self.ernie35_model},
            "groq": {"api_key": self.groq_api_key, "base_url": self.groq_base_url, "model": self.groq_model},
        }
        return providers.get(self.default_llm_provider, providers["deepseek"])

    # ============ 性能优化配置 ============
    # Pipeline 模式: "fast" = 并行搜索 + LLM抢占 | "legacy" = v6串行模式
    pipeline_mode: str = "fast"

    # 超时配置 (毫秒)
    pipeline_total_timeout_ms: int = 8000      # Pipeline 全局超时
    tool_execution_timeout_ms: int = 800       # 单工具执行超时
    llm_first_token_timeout_ms: int = 500      # LLM 首Token超时
    rag_search_timeout_ms: int = 500           # RAG搜索超时

    # 并行配置
    max_concurrent_searches: int = 3           # 并行搜索层数
    token_queue_size: int = 256                # Token 队列大小
    token_poll_interval_ms: int = 40           # Token 轮询间隔

    # 缓存配置
    redis_cache_ttl: int = 300                 # Redis 缓存 TTL (秒)
    bm25_index_cache_ttl: int = 60             # BM25 索引缓存 TTL (秒)

    # 分级路由
    enable_layered_routing: bool = True        # 启用 L1→L2→L3 分级查询
    redis_first_layer: bool = True             # Redis 作为第一层入口

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
