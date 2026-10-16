"""Tahlil yorumu uç noktaları: /api/labs/tests ve /api/labs/interpret."""

import threading
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from medrag import deps
from medrag.labs.interpret import catalog
from medrag.labs.service import LabService

router = APIRouter(prefix="/api/labs")

_lock = threading.Lock()
_service: dict[str, LabService] = {}


def get_lab_service() -> LabService:
    """Tembel kurulum; indeks yoksa kaynaksız (yalnızca kural tabanlı + LLM) çalışır."""
    if "svc" not in _service:
        with _lock:
            if "svc" not in _service:
                from medrag.llm import EvrenLLM

                settings = deps.get_settings()
                try:
                    retriever = deps.get_retriever()
                except Exception:  # noqa: BLE001 - indeks yoksa kaynaksız devam et
                    retriever = None
                llm = EvrenLLM(settings.llm_api_url, settings.labs_explain_model)
                _service["svc"] = LabService(retriever, llm)
    return _service["svc"]


class LabValue(BaseModel):
    test: str = Field(min_length=1, max_length=120)
    value: str | float
    unit: str | None = Field(default=None, max_length=30)
    ref_low: str | float | None = None
    ref_high: str | float | None = None

    @field_validator("value")
    @classmethod
    def _short(cls, v: str | float) -> str | float:
        if isinstance(v, str) and len(v) > 40:
            raise ValueError("değer çok uzun")
        return v


class InterpretRequest(BaseModel):
    sex: Literal["male", "female"] | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    values: list[LabValue] = Field(min_length=1, max_length=60)

    @field_validator("sex", mode="before")
    @classmethod
    def _sex(cls, v):
        return {"erkek": "male", "kadın": "female", "kadin": "female"}.get(v, v) if isinstance(v, str) else v


@router.get("/tests")
def tests() -> dict:
    return {"tests": catalog()}


@router.post("/interpret")
def interpret(req: InterpretRequest, service: Annotated[LabService, Depends(get_lab_service)]) -> dict:
    return service.interpret([v.model_dump() for v in req.values], sex=req.sex, age=req.age)
