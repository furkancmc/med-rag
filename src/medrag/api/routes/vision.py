"""Görsel okuma uç noktaları: tahlil fotoğrafı ve ilaç kutusu. Görseller saklanmaz."""

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from medrag import deps
from medrag.vision import ImageError, VisionClient, VisionError, VisionService

router = APIRouter(prefix="/api/vision")

_lock = threading.Lock()
_service: dict[str, VisionService] = {}


def get_vision_service() -> VisionService:
    if "svc" not in _service:
        with _lock:
            if "svc" not in _service:
                from medrag.llm import EvrenLLM

                s = deps.get_settings()
                _service["svc"] = VisionService(
                    VisionClient(s.vision_api_url),
                    EvrenLLM(s.vision_api_url, s.vision_extract_model),
                    [m.strip() for m in s.vision_ocr_models.split(",") if m.strip()],
                    s.vision_chat_model,
                    s.vision_max_bytes,
                )
    return _service["svc"]


def _run(fn, file: UploadFile, service: VisionService) -> dict:
    try:
        return fn(file.file.read(service.max_bytes + 1))  # sınırı aşan gövdeyi baştan okuma
    except ImageError as e:
        raise HTTPException(e.status, str(e)) from e
    except VisionError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/lab-report")
def lab_report(
    file: Annotated[UploadFile, File()], service: Annotated[VisionService, Depends(get_vision_service)]
) -> dict:
    return _run(service.lab_report, file, service)


@router.post("/medicine")
def medicine(
    file: Annotated[UploadFile, File()], service: Annotated[VisionService, Depends(get_vision_service)]
) -> dict:
    return _run(service.medicine, file, service)
