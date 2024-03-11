from typing import TypedDict, Literal


class Reporter(TypedDict):
    id: int
    full_name: str
    short_name: str
    start_year: int
    end_year: int
    slug: str


class ReporterVolume(TypedDict, total=False):
    id: str
    volume_number: str
    publisher: str
    publication_year: int
    start_year: int
    end_year: int
    reporter_slug: str


class JurisdictionFull(TypedDict):
    id: int
    name_long: str
    name: str
    slug: str
    reporters: list[Reporter]


class CourtMetadata(TypedDict):
    """
    {
        "name_abbreviation": "Cal. App. Dep't Super. Ct.",
        "id": 9003,
        "name": "Appellate Division of the Superior Court of the State of California"
    }
    """

    name_abbreviation: str
    id: int
    name: str


class CaseCitation(TypedDict):
    """
    {
        "type": "official",
        "cite": "8 Cal. App. 5th Supp. 1"
    }
    """

    type: str
    cite: str


class Jurisdiction(TypedDict):
    id: int
    name_long: str
    name: str


class Opinion(TypedDict):
    """
    {
        "text": "Opinion\n....\u2014\nI.\nIntroduction\nIn this appeal from an unlawful ...",
        "type": "majority",
        "author": "..."
    }
    """

    text: str
    type: Literal["majority"] | str
    author: str


class CaseBody(TypedDict, total=False):
    opinions: list[Opinion]


class CasePageRank(TypedDict):
    raw: float
    percentile: float


class CaseStats(TypedDict):
    cardinality: int
    char_count: int
    pagerank: CasePageRank
    sha265: str
    simhash: str
    word_count: int


class CaseMetadata(TypedDict, total=False):
    id: int
    name: str
    name_abbreviation: str
    decision_date: str
    court: CourtMetadata
    citations: list[CaseCitation]
    file_name: str
    casebody: CaseBody
    jurisdiction: Jurisdiction
    first_page: str
    last_page: str
    analysis: CaseStats
