"""Belirti değerlendirme uç noktaları (durumsuz; sağlık verisi sunucuda saklanmaz)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from medrag import deps
from medrag.assess.models import FinishRequest, FinishResponse, StartRequest, StartResponse
from medrag.assess.service import AssessService

router = APIRouter(prefix="/api/assess")


def get_assess_llm():
    """Değerlendirme için ayrı model (MEDRAG_ASSESS_MODEL); testlerde override edilir."""
    from medrag.llm import EvrenLLM

    settings = deps.get_settings()
    return deps._once("assess_llm", lambda: EvrenLLM(settings.llm_api_url, settings.assess_model))


def get_assess_service(
    llm: Annotated[object, Depends(get_assess_llm)],
    retriever: Annotated[object, Depends(deps.get_retriever)],
) -> AssessService:
    s = deps.get_settings()
    return AssessService(retriever, llm, s.assess_temperature, s.assess_max_tokens, s.assess_sources_k)


Service = Annotated[AssessService, Depends(get_assess_service)]


@router.post("/start", response_model=StartResponse)
def start(req: StartRequest, service: Service) -> StartResponse:
    return service.start(req)


@router.post("/finish", response_model=FinishResponse)
def finish(req: FinishRequest, service: Service) -> FinishResponse:
    try:
        return service.finish(req)
    except Exception as e:
        print(f"assess hatası: {type(e).__name__}")
        raise HTTPException(503, "Şu an değerlendirme yapılamıyor, lütfen biraz sonra tekrar deneyin.") from e
