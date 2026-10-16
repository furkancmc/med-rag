from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tüm ayarlar `MEDRAG_` önekli ortam değişkenleriyle değiştirilebilir.

    Her iş akışı kendi alanlarını kendi bloğunun altına ekler (paralel geliştirmede çakışmasın diye).
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MEDRAG_", extra="ignore")

    # --- Genel ---
    data_dir: Path = Path("data")
    top_k: int = 5

    # --- Arama ve embedding (iş akışı A) ---
    embed_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    embed_api_model: str = "qwen3-embedding-8b"
    embed_dimensions: int = 1024
    index_dir: Path = Path("data/index_qwen3")
    embed_workers: int = 16  # paralel embedding isteği (H200: yüksek eşzamanlılık)
    embed_query_cache_size: int = 1024  # sorgu embedding LRU önbelleği; 0 kapatır
    # Reranker: vektör aramadan `rerank_pool` aday alınır, yeniden sıralanıp ilk k döner.
    rerank_enabled: bool = False  # masraf nedeniyle kapalı (17.10.2026); açmak için MEDRAG_RERANK_ENABLED=true
    rerank_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    rerank_model: str = "qwen3-reranker-8b"
    rerank_pool: int = 40
    rerank_batch_size: int = 20  # istek başına doküman; gruplar paralel gider
    rerank_timeout: float = 20.0  # saniye, yeniden denemeler dahil; aşılırsa vektör sırası
    rerank_template: str = "qwen3"  # "qwen3": Qwen3-Reranker talimat şablonu, "none": ham metin
    rerank_instruction: str = ""  # boşsa varsayılan talimat (rerank.py)
    rerank_doc_chars: int = 1500  # rerank'e giden metin uzunluğu (4096 token bağlamına sığsın)
    # Çoklu sorgu: İngilizce çeviri + 1-2 Türkçe yeniden yazım, RRF ile birleşir (ölçülene kadar kapalı).
    multiquery_enabled: bool = False
    multiquery_model: str = "auto"
    multiquery_timeout: float = 15.0  # saniye; aşılırsa sadece orijinal sorgu kullanılır
    multiquery_original_weight: float = 1.0  # RRF'de orijinal sorgunun ağırlığı

    # --- Veri (iş akışı B) ---

    # --- Sohbet ve güvenlik (iş akışı C) ---
    llm_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    llm_model: str = "auto"

    # --- Belirti değerlendirme (iş akışı D) ---

    # --- Tahlil ve görsel okuma (iş akışı E) ---

    # --- Sunucu (iş akışı F) ---


def get_settings() -> Settings:
    return Settings()
