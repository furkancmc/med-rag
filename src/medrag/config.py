from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Eksik ya da hatalı yapılandırma (örn. EVREN_API_KEY yok). API bunu 503 olarak döner."""


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
    multiquery_model: str = "auto"  # deepseek düşünürken 8-22 sn sürüyor; hızlı yönlendirici seçildi
    multiquery_timeout: float = 15.0  # saniye; aşılırsa sadece orijinal sorgu kullanılır
    multiquery_original_weight: float = 1.0  # RRF'de orijinal sorgunun ağırlığı

    # --- Veri (iş akışı B) ---
    embed_batch_size: int = 64  # istek başına metin
    index_max_float16_mb: int = 40  # float16 bunu aşacaksa int8 sakla
    europepmc_per_topic: int = 3  # Europe PMC: konu başına makale

    # --- Sohbet ve güvenlik (iş akışı C) ---
    llm_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    llm_model: str = "deepseek-v4.1-flash"
    llm_extra_params: str = ""  # JSON; cevap modeline her isteğe eklenir (örn. düşünmeyi kapatma)
    answer_max_tokens: int = 4096  # düşünen modeller token harcar; cömert tutulur
    # Çalışma anında cevap doğrulama
    verify_enabled: bool = True
    verify_model: str = "deepseek-v4.1-flash"
    verify_extra_params: str = '{"chat_template_kwargs": {"enable_thinking": false}}'
    verify_budget_seconds: float = 20.0
    verify_group_size: int = 3
    verify_concurrency: int = 8
    # İkinci katman acil durum / zararlı istek sınıflandırıcısı
    classifier_enabled: bool = True
    guard_model: str = ""  # örn. qwen3-guard-4b; boşsa koruma modeli kullanılmaz (maliyet için kapalı)
    classifier_model: str = "deepseek-v4.1-flash"  # boş bırakılırsa LLM sınıflandırıcı kullanılmaz
    classifier_extra_params: str = '{"chat_template_kwargs": {"enable_thinking": false}}'
    classifier_timeout_seconds: float = 8.0

    # --- Belirti değerlendirme (iş akışı D) ---
    assess_model: str = "deepseek-v4.1-flash"
    assess_temperature: float = 0.2
    assess_max_tokens: int = 4000  # düşünen modeller için cömert
    assess_sources_k: int = 4

    # --- Tahlil ve görsel okuma (iş akışı E) ---
    labs_explain_model: str = "deepseek-v4.1-flash"
    vision_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    vision_ocr_models: str = "deepseek-ocr-2,dots-ocr"  # sırayla denenir; virgülle ayrılmış
    vision_chat_model: str = "qwen3-vl-30b"
    vision_extract_model: str = "deepseek-v4.1-flash"
    # Satır çıkarımı düşünmesiz çalışır (ölçüm: ~14 sn -> ~1,6 sn, aynı doğruluk)
    vision_extract_extra_params: str = '{"chat_template_kwargs": {"enable_thinking": false}}'
    vision_max_bytes: int = 8 * 1024 * 1024

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
