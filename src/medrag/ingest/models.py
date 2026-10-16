from dataclasses import asdict, dataclass


@dataclass
class Document:
    id: str
    title: str
    text: str
    source: str  # medlineplus | wikipedia | local
    url: str
    lang: str  # tr | en | es
    license: str


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    section: str
    text: str
    source: str
    url: str
    lang: str
    license: str

    def to_dict(self) -> dict:
        return asdict(self)
