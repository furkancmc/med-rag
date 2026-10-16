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

    # --- Veri (iş akışı B) ---

    # --- Sohbet ve güvenlik (iş akışı C) ---
    llm_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    llm_model: str = "auto"

    # --- Belirti değerlendirme (iş akışı D) ---

    # --- Tahlil ve görsel okuma (iş akışı E) ---

    # --- Sunucu (iş akışı F) ---
    access_code: str | None = None  # MEDRAG_ACCESS_CODE; doluysa /chat ve /api/* X-Access-Code ister
    # Hız sınırı (IP başına, token bucket): burst = en fazla ani istek, per_min = dakikadaki dolum.
    rate_limit_enabled: bool = True
    rate_chat_burst: int = 20  # /chat, /api/chat, /api/assess/*, /api/labs/interpret
    rate_chat_per_min: float = 30.0
    rate_upload_burst: int = 10  # /api/vision/*, /api/speech/*
    rate_upload_per_min: float = 12.0
    rate_api_burst: int = 60  # diğer /api/* uç noktaları
    rate_api_per_min: float = 120.0
    rate_max_buckets: int = 20000  # bellek sınırı: en eski kullanılan kova atılır
    # Ters vekil arkasında gerçek istemci IP'si: yalnızca ayar açıksa başlığa güvenilir.
    trust_proxy_headers: bool = False
    client_ip_header: str = "x-forwarded-for"
    proxy_hops: int = 1  # güvenilen vekil sayısı (X-Forwarded-For'da sağdan kaçıncı değer)
    # İstek gövdesi sınırları (bayt)
    max_json_bytes: int = 256 * 1024
    max_upload_bytes: int = 12 * 1024 * 1024
    csp: str = ""  # boşsa varsayılan Content-Security-Policy kullanılır
    hsts: bool = False  # yalnızca HTTPS arkasında aç
    access_log: bool = True  # yapılandırılmış JSON erişim logu (gövde ve başlık yazılmaz)
    log_client_ip: bool = False  # IP varsayılan olarak loga yazılmaz
    warmup: bool = False  # MEDRAG_WARMUP=1: açılışta indeksi arka planda yükle
    # Ses tanıma (Evren API, OpenAI uyumlu /audio/transcriptions)
    speech_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    speech_model: str = "qwen3-asr-1.7b"
    speech_language: str = "tr"
    speech_mode: str = "auto"  # auto | transcriptions | chat
    speech_timeout: float = 60.0
    speech_max_bytes: int = 10 * 1024 * 1024
    # Geri bildirim kaydı ({data_dir}/feedback/feedback.jsonl) ve döndürme
    feedback_max_bytes: int = 5 * 1024 * 1024
    feedback_keep: int = 3
    # Hakkında bilgisi: değerlendirme raporlarının klasörü
    eval_dir: Path = Path("eval")


def get_settings() -> Settings:
    return Settings()
