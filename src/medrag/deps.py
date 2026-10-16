"""Paylaşılan, tembel yüklenen bağımlılıklar.

API rotaları bunları FastAPI `Depends` ile kullanır; testlerde `app.dependency_overrides` ile
sahte nesnelerle değiştirilir. İndeks ve istemciler ilk kullanımda bir kez oluşturulur.
"""

import threading
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from medrag.config import Settings

_lock = threading.Lock()
_cache: dict[str, Any] = {}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _once(name: str, factory: Callable[[], Any]) -> Any:
    if name not in _cache:
        with _lock:
            if name not in _cache:
                _cache[name] = factory()
    return _cache[name]


def get_retriever():
    from medrag.retrieve import load_retriever

    return _once("retriever", lambda: load_retriever(get_settings()))


def get_llm():
    from medrag.llm import EvrenLLM

    settings = get_settings()
    return _once("llm", lambda: EvrenLLM(settings.llm_api_url, settings.llm_model))


def get_chat_service():
    from medrag.chat.service import ChatService

    return _once(
        "chat_service", lambda: ChatService(get_retriever(), get_llm(), get_settings().top_k)
    )


def is_ready() -> bool:
    return "retriever" in _cache


def reset() -> None:
    """Testler için: önbelleği temizler."""
    _cache.clear()
    get_settings.cache_clear()
