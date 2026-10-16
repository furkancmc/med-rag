from dataclasses import asdict, dataclass


@dataclass
class Document:
    id: str
    title: str
    text: str
    source: str  # medlineplus | wikipedia | europepmc | openfda | nihods | local
    url: str
    lang: str  # tr | en | es
    license: str
    published: str = ""  # yayın/güncelleme tarihi: ISO tarih ya da yıl, bilinmiyorsa boş
    retrieved_at: str = ""  # verinin çekildiği ISO tarih
    citation: str = ""  # kaynak gösterimi (dergi, yazar, doi vb.); yoksa boş


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
    published: str = ""
    retrieved_at: str = ""
    citation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
