"""İstek ve cevap modelleri ile seviye sıralaması."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Level = Literal["emergency", "today", "soon", "home"]
LEVEL_ORDER: dict[str, int] = {"home": 0, "soon": 1, "today": 2, "emergency": 3}
LEVEL_LABELS: dict[str, str] = {
    "emergency": "Hemen 112'yi arayın",
    "today": "Bugün bir hekime başvurun",
    "soon": "Birkaç gün içinde randevu alın",
    "home": "Evde izleyebilirsiniz",
}
DISCLAIMER = (
    "Bu değerlendirme genel bilgilendirme amaçlıdır; teşhis ya da tedavi yerine geçmez. "
    "Durumunuz kötüleşirse veya endişeleniyorsanız bir hekime başvurun, acil durumda 112'yi arayın."
)


def max_level(a: str, b: str) -> str:
    return a if LEVEL_ORDER[a] >= LEVEL_ORDER[b] else b


class Profile(BaseModel):
    age: int | None = Field(default=None, ge=0, le=120)
    age_months: int | None = Field(default=None, ge=0, le=36, description="Bebekler için ay")
    sex: Literal["kadın", "erkek"] | None = None
    pregnant: bool | None = None
    chronic: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("chronic")
    @classmethod
    def _short_items(cls, v: list[str]) -> list[str]:
        return [s.strip()[:60] for s in v if s and s.strip()]


class StartRequest(Profile):
    complaint: str = Field(min_length=2, max_length=500)

    @field_validator("complaint")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("şikâyet boş olamaz")
        return v.strip()


class Question(BaseModel):
    id: str
    text: str
    type: Literal["single", "multi", "scale", "text"] = "text"
    options: list[str] | None = None
    why: str | None = None


class StartResponse(BaseModel):
    emergency: bool = False
    emergency_text: str | None = None
    questions: list[Question] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


class Answer(BaseModel):
    id: str = Field(max_length=40)
    question: str = Field(max_length=300)
    answer: str = Field(max_length=500)


class FinishRequest(BaseModel):
    complaint: str = Field(min_length=2, max_length=500)
    profile: Profile = Field(default_factory=Profile)
    answers: list[Answer] = Field(default_factory=list, max_length=10)


class SourceCard(BaseModel):
    n: int
    title: str
    url: str = ""
    source: str = ""
    license: str = ""


class FinishResponse(BaseModel):
    level: Level
    level_label: str
    summary: str
    reasons: list[str] = Field(default_factory=list)
    red_flags_to_watch: list[str] = Field(default_factory=list)
    self_care: list[str] = Field(default_factory=list)
    sources: list[SourceCard] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


class LLMAssessment(BaseModel):
    """LLM'nin döndürmesi beklenen katı JSON."""

    level: Level
    summary: str = Field(min_length=1)
    reasons: list[str] = Field(default_factory=list)
    red_flags_to_watch: list[str] = Field(default_factory=list)
    self_care: list[str] = Field(default_factory=list)

    @field_validator("reasons", "red_flags_to_watch", "self_care", mode="before")
    @classmethod
    def _list_of_str(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v if str(x).strip()]
