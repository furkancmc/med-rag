"""Sık istenen tahliller için yetişkin referans aralıkları.

DİKKAT: Aralıklar laboratuvardan laboratuvara değişir. Kullanıcının kendi rapordaki aralığı
her zaman bu tablodan önceliklidir (bkz. interpret.py). Her kayıtta aralığın kaynağı ve genel bilgi
sayfası (MedlinePlus, kamu malı) bulunur. Kritik eşikler yaygın klinik "panik değer" listelerinden
alınmış muhafazakâr değerlerdir; hekim değerlendirmesinin yerine geçmez.
"""

from dataclasses import dataclass, field

ML = "https://medlineplus.gov/lab-tests/"
SRC_ML = "MedlinePlus (ABD Ulusal Tıp Kütüphanesi) tipik yetişkin aralığı"
SRC_MAYO = "Mayo Clinic Laboratories tipik yetişkin aralığı"
SRC_CLIN = "Yaygın klinik hedef/eşik değeri (MedlinePlus ve ilgili rehberler)"

Range = tuple[float | None, float | None]


@dataclass(frozen=True)
class LabTest:
    id: str
    name: str
    unit: str  # kanonik birim; aralıklar bu birimdedir
    ranges: dict[str, Range]  # "all" ya da "male"/"female"
    aliases: tuple[str, ...] = ()
    # Diğer birim -> (çarpan, ofset): kanonik = değer * çarpan + ofset
    units: dict[str, tuple[float, float]] = field(default_factory=dict)
    crit_low: float | None = None
    crit_high: float | None = None
    description: str = ""
    url: str = ""
    ref_source: str = SRC_ML
    group: str = ""

    def to_catalog(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "group": self.group,
            "unit": self.unit,
            "units": [self.unit, *self.units],
            "aliases": list(self.aliases),
            "ranges": {k: {"low": v[0], "high": v[1]} for k, v in self.ranges.items()},
            "sex_specific": "male" in self.ranges,
            "description": self.description,
            "url": self.url,
            "ref_source": self.ref_source,
        }


def _t(**kw) -> LabTest:
    return LabTest(**kw)


TESTS: tuple[LabTest, ...] = (
    # --- Hemogram ---
    _t(
        id="hemoglobin", name="Hemoglobin", group="Hemogram", unit="g/dL",
        ranges={"male": (13.8, 17.2), "female": (12.1, 15.1)},
        aliases=("hgb", "hb", "hemoglobin", "hemoglobulin"),
        units={"g/L": (0.1, 0), "mmol/L": (1.611, 0)},
        crit_low=7.0, crit_high=20.0,
        description="Kanda oksijen taşıyan alyuvar proteinidir. Düşüklüğü kansızlık (anemi) ile ilişkili olabilir.",
        url=ML + "hemoglobin-test/",
    ),
    _t(
        id="hematocrit", name="Hematokrit", group="Hemogram", unit="%",
        ranges={"male": (40.7, 50.3), "female": (36.1, 44.3)},
        aliases=("hct", "hematokrit", "hematocrit"),
        units={"L/L": (100, 0)},
        crit_low=21.0, crit_high=60.0,
        description="Kanın ne kadarının alyuvarlardan oluştuğunu gösterir.",
        url=ML + "hematocrit-test/",
    ),
    _t(
        id="wbc", name="Lökosit (akyuvar)", group="Hemogram", unit="10^3/µL",
        ranges={"all": (4.5, 11.0)},
        aliases=("wbc", "lökosit", "lokosit", "akyuvar", "beyaz küre", "beyaz kan hücresi", "white blood cell"),
        units={"/µL": (0.001, 0), "/mm3": (0.001, 0), "10^9/L": (1.0, 0)},
        crit_low=2.0, crit_high=30.0,
        description="Enfeksiyonla savaşan akyuvar hücrelerinin sayısıdır.",
        url=ML + "white-blood-count-wbc/",
    ),
    _t(
        id="platelet", name="Trombosit", group="Hemogram", unit="10^3/µL",
        ranges={"all": (150.0, 450.0)},
        aliases=("plt", "trombosit", "platelet", "kan pulcuğu", "kan pulu"),
        units={"/µL": (0.001, 0), "/mm3": (0.001, 0), "10^9/L": (1.0, 0)},
        crit_low=20.0, crit_high=1000.0,
        description="Kanın pıhtılaşmasına yardım eden hücre parçacıklarının sayısıdır.",
        url=ML + "platelet-tests/",
    ),
    _t(
        id="rbc", name="Eritrosit (alyuvar)", group="Hemogram", unit="10^6/µL",
        ranges={"male": (4.7, 6.1), "female": (4.2, 5.4)},
        aliases=("rbc", "eritrosit", "alyuvar", "kırmızı küre", "red blood cell"),
        units={"/µL": (1e-6, 0), "/mm3": (1e-6, 0), "10^12/L": (1.0, 0)},
        description="Oksijen taşıyan alyuvar hücrelerinin sayısıdır.",
        url=ML + "red-blood-cell-rbc-count/",
    ),
    _t(
        id="mcv", name="MCV (ortalama alyuvar hacmi)", group="Hemogram", unit="fL",
        ranges={"all": (80.0, 100.0)},
        aliases=("mcv", "ortalama eritrosit hacmi", "ortalama alyuvar hacmi"),
        description="Alyuvarların ortalama büyüklüğüdür; kansızlığın türünü ayırt etmeye yardımcı olur.",
        url=ML + "complete-blood-count-cbc/",
        ref_source=SRC_ML,
    ),
    # --- Şeker ---
    _t(
        id="glucose", name="Açlık kan şekeri (glukoz)", group="Şeker", unit="mg/dL",
        ranges={"all": (70.0, 99.0)},
        aliases=("glukoz", "glucose", "açlık kan şekeri", "aclik kan sekeri", "kan şekeri", "aks", "fbg", "fasting glucose"),
        units={"mmol/L": (18.016, 0)},
        crit_low=40.0, crit_high=500.0,
        description="Kandaki şeker düzeyidir. Açlık değeri için 100 mg/dL ve üzeri şeker hastalığı açısından değerlendirme gerektirebilir.",
        url=ML + "blood-glucose-test/",
        ref_source=SRC_CLIN,
    ),
    _t(
        id="hba1c", name="HbA1c (glikozile hemoglobin)", group="Şeker", unit="%",
        ranges={"all": (4.0, 5.6)},
        aliases=("hba1c", "a1c", "hemoglobin a1c", "hb a1c", "glikozile hemoglobin", "glikolize hemoglobin", "glycated hemoglobin"),
        units={"mmol/mol": (0.09148, 2.152)},
        crit_high=15.0,
        description="Son 2-3 aydaki ortalama kan şekerini yansıtır. %5,7-6,4 arası öncül, %6,5 ve üzeri şeker hastalığı aralığıdır.",
        url=ML + "hemoglobin-a1c-hba1c-test/",
        ref_source=SRC_CLIN,
    ),
    # --- Yağlar ---
    _t(
        id="cholesterol", name="Total kolesterol", group="Kan yağları", unit="mg/dL",
        ranges={"all": (None, 200.0)},
        aliases=("kolesterol", "total kolesterol", "cholesterol", "total cholesterol", "tc", "chol"),
        units={"mmol/L": (38.67, 0)},
        description="Kandaki toplam kolesterol miktarıdır; 200 mg/dL altı istenen düzeydir.",
        url=ML + "cholesterol-levels/",
        ref_source=SRC_CLIN,
    ),
    _t(
        id="ldl", name="LDL kolesterol", group="Kan yağları", unit="mg/dL",
        ranges={"all": (None, 129.0)},
        aliases=("ldl", "ldl kolesterol", "ldl-c", "ldl cholesterol", "kötü kolesterol"),
        units={"mmol/L": (38.67, 0)},
        description="'Kötü' kolesterol olarak bilinir. 100 altı ideal, 130-159 sınırda yüksektir; kişinin kalp riskine göre hedef değişir.",
        url=ML + "cholesterol-levels/",
        ref_source=SRC_CLIN,
    ),
    _t(
        id="hdl", name="HDL kolesterol", group="Kan yağları", unit="mg/dL",
        ranges={"male": (40.0, None), "female": (50.0, None)},
        aliases=("hdl", "hdl kolesterol", "hdl-c", "hdl cholesterol", "iyi kolesterol"),
        units={"mmol/L": (38.67, 0)},
        description="'İyi' kolesterol olarak bilinir; düşük olması kalp-damar riski açısından olumsuzdur.",
        url=ML + "cholesterol-levels/",
        ref_source=SRC_CLIN,
    ),
    _t(
        id="triglyceride", name="Trigliserid", group="Kan yağları", unit="mg/dL",
        ranges={"all": (None, 149.0)},
        aliases=("trigliserid", "trigliserit", "triglyceride", "triglycerides", "tg", "trig"),
        units={"mmol/L": (88.57, 0)},
        crit_high=1000.0,
        description="Kandaki yağ türlerinden biridir. 150 mg/dL altı normaldir; çok yüksek değerler pankreas iltihabı riski taşıyabilir.",
        url=ML + "triglycerides-test/",
        ref_source=SRC_CLIN,
    ),
    # --- Böbrek ---
    _t(
        id="creatinine", name="Kreatinin", group="Böbrek", unit="mg/dL",
        ranges={"male": (0.74, 1.35), "female": (0.59, 1.04)},
        aliases=("kreatinin", "creatinine", "creat", "crea", "kr"),
        units={"µmol/L": (0.01131, 0)},
        crit_high=7.4,
        description="Böbreklerin süzme işlevini değerlendirmeye yarayan bir kas atık ürünüdür.",
        url=ML + "creatinine-test/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="urea", name="Üre", group="Böbrek", unit="mg/dL",
        ranges={"all": (13.0, 51.0)},
        aliases=("üre", "ure", "urea", "kan üresi", "serum üre"),
        units={"mmol/L": (6.006, 0)},
        description="Protein yıkımının atık ürünüdür; böbrek işlevi ve sıvı dengesiyle ilgilidir. (BUN x 2,14 ile ilişkilidir.)",
        url=ML + "bun-blood-urea-nitrogen/",
        ref_source=SRC_ML + " (BUN 6-24 mg/dL x 2,14 üre dönüşümü)",
    ),
    _t(
        id="bun", name="BUN (kan üre azotu)", group="Böbrek", unit="mg/dL",
        ranges={"all": (6.0, 24.0)},
        aliases=("bun", "kan üre azotu", "üre azotu", "blood urea nitrogen", "urea nitrogen"),
        units={"mmol/L": (2.801, 0)},
        description="Kandaki üre azotudur; böbrek işlevi ve sıvı dengesiyle ilgilidir.",
        url=ML + "bun-blood-urea-nitrogen/",
    ),
    _t(
        id="uric_acid", name="Ürik asit", group="Böbrek", unit="mg/dL",
        ranges={"male": (3.4, 7.0), "female": (2.4, 6.0)},
        aliases=("ürik asit", "urik asit", "uric acid", "ua", "ürat"),
        units={"µmol/L": (0.01681, 0)},
        description="Pürin yıkımının ürünüdür; yüksekliği gut hastalığı ve böbrek taşı ile ilişkili olabilir.",
        url=ML + "uric-acid-test/",
        ref_source=SRC_MAYO,
    ),
    # --- Karaciğer ---
    _t(
        id="alt", name="ALT (SGPT)", group="Karaciğer", unit="U/L",
        ranges={"male": (7.0, 55.0), "female": (7.0, 45.0)},
        aliases=("alt", "sgpt", "alanin aminotransferaz", "alanine aminotransferase", "alt (sgpt)"),
        description="Karaciğer hücrelerinde bulunan bir enzimdir; karaciğer hücre hasarında yükselebilir.",
        url=ML + "alt-blood-test/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="ast", name="AST (SGOT)", group="Karaciğer", unit="U/L",
        ranges={"male": (8.0, 48.0), "female": (8.0, 43.0)},
        aliases=("ast", "sgot", "aspartat aminotransferaz", "aspartate aminotransferase", "ast (sgot)"),
        description="Karaciğer ve kasta bulunan bir enzimdir; karaciğer ya da kas hasarında yükselebilir.",
        url=ML + "ast-test/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="ggt", name="GGT (gama GT)", group="Karaciğer", unit="U/L",
        ranges={"male": (8.0, 61.0), "female": (5.0, 36.0)},
        aliases=("ggt", "gama gt", "gamma gt", "gama glutamil transferaz", "gamma-glutamyl transferase", "g-gt"),
        description="Karaciğer ve safra yollarıyla ilgili bir enzimdir.",
        url=ML + "gamma-glutamyl-transferase-ggt-test/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="alp", name="ALP (alkalen fosfataz)", group="Karaciğer", unit="U/L",
        ranges={"all": (40.0, 129.0)},
        aliases=("alp", "alkalen fosfataz", "alkaline phosphatase", "alk fosfataz"),
        description="Karaciğer, safra yolları ve kemikte bulunan bir enzimdir.",
        url=ML + "alkaline-phosphatase/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="bilirubin", name="Total bilirubin", group="Karaciğer", unit="mg/dL",
        ranges={"all": (0.1, 1.2)},
        aliases=("bilirubin", "total bilirubin", "t. bilirubin", "t.bil", "tbil", "bilirübin"),
        units={"µmol/L": (0.0585, 0)},
        crit_high=15.0,
        description="Alyuvar yıkımından oluşan sarı pigmenttir; yüksekliği sarılığa yol açabilir.",
        url=ML + "bilirubin-blood-test/",
    ),
    _t(
        id="albumin", name="Albümin", group="Karaciğer", unit="g/dL",
        ranges={"all": (3.5, 5.0)},
        aliases=("albümin", "albumin", "alb"),
        units={"g/L": (0.1, 0)},
        description="Karaciğerin yaptığı başlıca kan proteinidir; beslenme ve karaciğer/böbrek durumu hakkında fikir verir.",
        url=ML + "albumin-blood-test/",
    ),
    # --- Tiroit ---
    _t(
        id="tsh", name="TSH", group="Tiroit", unit="mIU/L",
        ranges={"all": (0.4, 4.0)},
        aliases=("tsh", "tiroid uyarıcı hormon", "tiroit uyarıcı hormon", "thyroid stimulating hormone", "tiroid stimulan hormon"),
        units={"µIU/mL": (1.0, 0), "uIU/mL": (1.0, 0)},
        description="Hipofizin tiroit bezini uyaran hormonudur. Yüksekliği tiroitin yavaş, düşüklüğü hızlı çalışmasıyla ilişkili olabilir.",
        url=ML + "tsh-thyroid-stimulating-hormone-test/",
    ),
    _t(
        id="ft4", name="Serbest T4 (sT4)", group="Tiroit", unit="ng/dL",
        ranges={"all": (0.8, 1.8)},
        aliases=("ft4", "st4", "serbest t4", "free t4", "sT4", "t4 serbest", "fT4"),
        units={"pmol/L": (0.0777, 0)},
        description="Tiroit bezinin ürettiği ve kanda serbest dolaşan hormondur.",
        url=ML + "thyroxine-t4-test/",
    ),
    # --- Vitamin / mineral ---
    _t(
        id="ferritin", name="Ferritin", group="Vitamin ve mineral", unit="ng/mL",
        ranges={"male": (24.0, 336.0), "female": (11.0, 307.0)},
        aliases=("ferritin", "ferritin düzeyi"),
        units={"µg/L": (1.0, 0), "ug/L": (1.0, 0)},
        description="Vücudun demir depolarını yansıtır; düşüklüğü demir eksikliğinin erken göstergesi olabilir.",
        url=ML + "ferritin-blood-test/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="iron", name="Demir (serum)", group="Vitamin ve mineral", unit="µg/dL",
        ranges={"male": (65.0, 175.0), "female": (50.0, 170.0)},
        aliases=("demir", "serum demir", "iron", "fe", "serum iron"),
        units={"µmol/L": (5.585, 0)},
        description="Kandaki demir miktarıdır; gün içinde ve besinlerle çok değişebilir.",
        url=ML + "iron-tests/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="b12", name="B12 vitamini", group="Vitamin ve mineral", unit="pg/mL",
        ranges={"all": (200.0, 900.0)},
        aliases=("b12", "vitamin b12", "b12 vitamini", "kobalamin", "cobalamin", "vit b12", "b-12"),
        units={"pmol/L": (1.355, 0), "ng/L": (1.0, 0)},
        description="Sinir sistemi ve kan yapımı için gereken vitamindir.",
        url=ML + "vitamin-b-test/",
    ),
    _t(
        id="folate", name="Folat (folik asit)", group="Vitamin ve mineral", unit="ng/mL",
        ranges={"all": (4.0, None)},
        aliases=("folat", "folik asit", "folate", "folic acid", "vitamin b9", "b9"),
        units={"nmol/L": (0.4414, 0)},
        description="Hücre yapımı ve kan yapımı için gereken B grubu vitamindir.",
        url=ML + "vitamin-b-test/",
        ref_source=SRC_MAYO,
    ),
    _t(
        id="vitamin_d", name="D vitamini (25-OH)", group="Vitamin ve mineral", unit="ng/mL",
        ranges={"all": (20.0, 100.0)},
        aliases=("d vitamini", "vitamin d", "25-oh vitamin d", "25 oh d vitamini", "25-oh d", "25-hidroksi vitamin d", "25(oh)d", "vit d", "d vit"),
        units={"nmol/L": (0.4006, 0)},
        crit_high=150.0,
        description="Kemik sağlığı için önemli bir vitamindir. 20 ng/mL altı yetersizlik olarak değerlendirilir.",
        url=ML + "vitamin-d-test/",
        ref_source="NIH Beslenme Takviyeleri Ofisi (D vitamini bilgi notu) ve Mayo Clinic Laboratories",
    ),
    # --- İltihap / elektrolit ---
    _t(
        id="crp", name="CRP", group="İltihap", unit="mg/L",
        ranges={"all": (0.0, 5.0)},
        aliases=("crp", "c-reaktif protein", "c reaktif protein", "c-reactive protein", "creaktif protein"),
        units={"mg/dL": (10.0, 0)},
        description="Vücutta iltihap olduğunda karaciğerin yaptığı bir proteindir; nedenini tek başına göstermez.",
        url=ML + "c-reactive-protein-crp-test/",
        ref_source=SRC_CLIN,
    ),
    _t(
        id="sodium", name="Sodyum", group="Elektrolit", unit="mmol/L",
        ranges={"all": (135.0, 145.0)},
        aliases=("sodyum", "na", "sodium", "na+"),
        units={"mEq/L": (1.0, 0)},
        crit_low=120.0, crit_high=160.0,
        description="Vücudun sıvı dengesi ve sinir-kas işlevi için gerekli bir elektrolittir.",
        url=ML + "sodium-blood-test/",
    ),
    _t(
        id="potassium", name="Potasyum", group="Elektrolit", unit="mmol/L",
        ranges={"all": (3.6, 5.2)},
        aliases=("potasyum", "k", "potassium", "k+"),
        units={"mEq/L": (1.0, 0)},
        crit_low=2.5, crit_high=6.5,
        description="Kalp ritmi ve kas işlevi için kritik bir elektrolittir.",
        url=ML + "potassium-blood-test/",
    ),
    _t(
        id="chloride", name="Klor", group="Elektrolit", unit="mmol/L",
        ranges={"all": (98.0, 107.0)},
        aliases=("klor", "klorür", "chloride", "cl", "cl-"),
        units={"mEq/L": (1.0, 0)},
        description="Sıvı ve asit-baz dengesiyle ilgili elektrolittir.",
        url=ML + "chloride-blood-test/",
    ),
    _t(
        id="calcium", name="Kalsiyum (total)", group="Elektrolit", unit="mg/dL",
        ranges={"all": (8.6, 10.3)},
        aliases=("kalsiyum", "ca", "calcium", "total kalsiyum", "serum kalsiyum"),
        units={"mmol/L": (4.008, 0)},
        crit_low=6.5, crit_high=13.0,
        description="Kemik, kas ve sinir işlevi için gereken minerali gösterir.",
        url=ML + "calcium-blood-test/",
    ),
)

BY_ID: dict[str, LabTest] = {t.id: t for t in TESTS}
SEXES = ("male", "female")
