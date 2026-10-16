"""POST /api/speech/transcribe — ses dosyasını metne çevirir (ses saklanmaz, loglanmaz)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from medrag import deps
from medrag.config import Settings
from medrag.speech import AUDIO_TYPES, SpeechClient, SpeechError, normalize_type, sniff_audio

router = APIRouter(prefix="/api/speech")


def get_speech_client(settings: Annotated[Settings, Depends(deps.get_settings)]) -> SpeechClient:
    return SpeechClient(
        settings.speech_api_url,
        settings.speech_model,
        settings.speech_language,
        settings.speech_mode,
        settings.speech_timeout,
    )


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


@router.post("/transcribe")
def transcribe(
    file: Annotated[UploadFile, File()],
    settings: Annotated[Settings, Depends(deps.get_settings)],
    client: Annotated[SpeechClient, Depends(get_speech_client)],
):
    limit = settings.speech_max_bytes
    declared = normalize_type(file.content_type)
    if declared not in AUDIO_TYPES:
        return _error(415, "unsupported_media_type", "Desteklenmeyen ses biçimi.")
    data = file.file.read(limit + 1)
    if len(data) > limit:
        return _error(413, "payload_too_large", "Ses dosyası çok büyük (en fazla 10 MB).")
    if not data:
        return _error(400, "empty_audio", "Ses dosyası boş.")
    sniffed = sniff_audio(data)
    if sniffed is None:
        return _error(415, "unsupported_media_type", "Dosya geçerli bir ses kaydı değil.")
    try:
        text = client.transcribe(data, sniffed)
    except SpeechError as e:
        return _error(502, "speech_failed", str(e))
    if not text:
        return _error(422, "no_speech", "Konuşma algılanamadı, lütfen tekrar deneyin.")
    return {"text": text}
