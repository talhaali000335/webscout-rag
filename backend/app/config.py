from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=("settings_",))

    # LLM: Groq (free key at https://console.groq.com/keys). OpenAI-compatible API.
    groq_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"   # faster/cheaper alternative: llama-3.1-8b-instant
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Infra
    redis_url: str = "redis://redis:6379/0"
    data_dir: str = "/data"        # vectors + saved browser sessions live here (docker volume)

    # Models (small ONNX models, run on CPU, no GPU needed)
    embed_model: str = "BAAI/bge-small-en-v1.5"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    model_cache_dir: str = "/models"

    # RAG tuning
    chunk_chars: int = 1000
    chunk_overlap: int = 150
    retrieve_k: int = 20          # candidates from the vector store
    final_k: int = 5              # passages sent to the LLM after re-ranking
    rerank_min_score: float = -1.0  # below this the passage is "irrelevant" -> dropped

    # Misc
    cache_ttl: int = 21600        # 6h: re-asking the same URL skips scraping
    vector_ttl_days: int = 7      # old vector files are deleted
    login_timeout: int = 300      # seconds we wait for the human to sign in
    rate_limit_per_min: int = 30
    cors_origins: str = "*"


settings = Settings()
