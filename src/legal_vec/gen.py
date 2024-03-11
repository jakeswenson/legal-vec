import zipfile

import click
import rich
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer

from legal_vec import downloads_dir, CaseMetadata, parse_json, Opinion
from alive_progress import alive_bar
import sys
from dataclasses import dataclass
from typing import Any, Iterable

COLLECTION_NAME = "cases"

allowed_opinions = {
    "majority": 1,
    "unanimous": 1,
    "on-the-merits": 1,
    "rehearing": 2,
    "concurrence": 3,
    "concurring-in-part-and-dissenting-in-part": 4,
}


@dataclass
class LoadedCase:
    case: CaseMetadata
    opinion_type: str
    text: str


def load_case(case_file: zipfile.Path):
    case: CaseMetadata = parse_json(case_file)

    body = case["casebody"]
    cite = next(
        map(
            lambda c: c["cite"],
            filter(lambda c: c["type"] == "official", case["citations"]),
        ),
        case["decision_date"],
    )

    # rich.print(f"[blue]{case['name_abbreviation']} [green]{cite}")

    opinions = body["opinions"]

    if not opinions:
        return

    try:
        if len(opinions) == 1:
            opinion: Opinion = opinions[0]
        else:
            opinion: Opinion = sorted(
                filter(lambda o: o["type"] in allowed_opinions, body["opinions"]),
                key=lambda o: allowed_opinions[o["type"]],
            )[0]
    except (StopIteration, IndexError):
        types = list(map(lambda o: o["type"], opinions))
        rich.print(f"[red] {cite} error selecting opinion from options: {types}")
        return
    # print(opinion["text"])
    text = opinion["text"]
    paragraphs = text.splitlines()

    if len(paragraphs) < 5 or len(text) < 150:
        return

    return LoadedCase(case, opinion_type=opinion["type"], text=text)


@dataclass
class EncodedCase:
    case: LoadedCase
    vec: Any


def encode_batch(cases: list[LoadedCase], model: SentenceTransformer) -> list[EncodedCase]:
    vectors = model.encode([case.text for case in cases])

    return [EncodedCase(case, vec.tolist()) for (case, vec) in zip(cases, vectors)]


def insert_batch(case_encodings: list[EncodedCase], client: QdrantClient):
    client.upsert(
        COLLECTION_NAME,
        wait=True,
        points=[
            PointStruct(
                id=case.case.case["id"],
                vector=case.vec,
                payload={
                    "case_id": case.case.case["id"],
                    "date": case.case.case["decision_date"],
                    "citations": [cite["cite"] for cite in case.case.case["citations"]],
                    "jurisdiction": case.case.case["jurisdiction"],
                    "court": case.case.case["court"],
                    "first_page": case.case.case["first_page"],
                    "last_page": case.case.case["last_page"],
                    "file_name": case.case.case["file_name"],
                    "name_short": case.case.case["name_abbreviation"],
                    "name": case.case.case["name"],
                    "opinion_type": case.case.opinion_type,
                },
            )
            for case in case_encodings
        ],
    )


def build_db(case_file: zipfile.Path, client: QdrantClient, model: SentenceTransformer):

    case = load_case(case_file)

    if client.retrieve(COLLECTION_NAME, [case.case["id"]]):
        return

    vector = model.encode(case.text)

    client.upsert(
        COLLECTION_NAME,
        wait=True,
        points=[
            PointStruct(
                id=case.case["id"],
                vector=vector.tolist(),
                payload={
                    "case_id": case.case["id"],
                    "date": case.case["decision_date"],
                    "citations": [cite["cite"] for cite in case.case["citations"]],
                    "jurisdiction": case.case["jurisdiction"],
                    "court": case.case["court"],
                    "first_page": case.case["first_page"],
                    "last_page": case.case["last_page"],
                    "file_name": case.case["file_name"],
                    "name_short": case.case["name_abbreviation"],
                    "name": case.case["name"],
                },
            )
        ],
    )


@click.command()
def train():
    rich.print("[yellow]Loading existing DB")
    client = QdrantClient(path="./case-db")

    rich.print("[blue]Setting up model")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    rich.print("[yellow]Gathering zips")

    zips = downloads_dir.glob("*/*.zip")

    rich.print("[yellow]Zips gathered")
    # cases_dir.glob("*/json/*.json")
    if client.collection_exists(COLLECTION_NAME):
        col = client.get_collection(COLLECTION_NAME)
        pass
    else:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=model.get_sentence_embedding_dimension(), distance=Distance.COSINE
            ),
        )

    # cases: Iterator[CaseMetadata] = (parse_json(p) for p in case_files)

    # cases = itertools.islice(cases, 10)
    rich.print("[green]Starting generation...")
    with alive_bar(unknown="radioactive") as bar:
        for zip_path in zips:
            zip = zipfile.ZipFile(zip_path)
            bar.text = f"{zip_path.parent.name}/{zip_path.stem}"
            try:
                cases: list[LoadedCase] = []

                for case_file in zipfile.Path(zip, "json/").iterdir():
                    loaded_case = load_case(case_file)
                    if not loaded_case:
                        bar()
                        continue

                    cases.append(loaded_case)

                case_ids = {case.case["id"] for case in cases}

                existing = {rec.id for rec in client.retrieve(COLLECTION_NAME, list(case_ids))}
                case_ids.difference_update(existing)

                if not case_ids:
                    bar(len(cases))
                    continue

                cases = [case for case in cases if case.case["id"] in case_ids]

                bar.text = f"{zip_path.parent.name}/{zip_path.stem} training {len(cases)} (skipped {len(existing)})"

                encodings = encode_batch(cases, model)
                insert_batch(encodings, client)
                bar(len(cases))
                # for case_file in zipfile.Path(zip, "json/").iterdir():
                #     # bar.text = f"{zip_path.parent.name}/{zip_path.stem}/{case_file.name}"
                #     build_db(case_file, client, model)
                #     bar()
            except zipfile.BadZipfile:
                rich.print(f"[red]Bad Zip: {case_file}", file=sys.stderr)
                bar()
                continue

    query = input("Query: ")
    vecs = model.encode(query)

    hits = client.search(collection_name="cases", query_vector=vecs.tolist(), limit=2)

    print(hits)
