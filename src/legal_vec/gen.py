import zipfile

import click
import rich
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer

from legal_vec import downloads_dir, CaseMetadata, parse_json, Opinion
from alive_progress import alive_bar
import sys

COLLECTION_NAME = "cases"

allowed_opinions = {"majority": 1, "unanimous": 1, "concurring-in-part-and-dissenting-in-part": 2}


def build_db(case_file: zipfile.Path, client, model, progress):
    try:
        case: CaseMetadata = parse_json(case_file)
    except zipfile.BadZipfile:
        rich.print("[red]Bad Zip:", case_file, file=sys.stderr)
        progress()
        return

    if client.retrieve(COLLECTION_NAME, [case["id"]]):
        progress()
        return

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
        progress()
        return

    try:
        opinion: Opinion = sorted(
            filter(lambda o: o["type"] in allowed_opinions, body["opinions"]),
            key=lambda o: allowed_opinions[o["type"]],
        )[0]
    except StopIteration:
        types = list(map(lambda o: o["type"], opinions))
        rich.print("[red] {cite} Opinions: {types}")
        progress()
        return
    # print(opinion["text"])
    text = opinion["text"]
    paragraphs = text.splitlines()

    if len(paragraphs) < 5 or len(text) < 150:
        progress()
        return

    vector = model.encode(text)
    client.upsert(
        COLLECTION_NAME,
        wait=True,
        points=[
            PointStruct(
                id=case["id"],
                vector=vector.tolist(),
                payload={
                    "case_id": case["id"],
                    "date": case["decision_date"],
                    "citations": [cite["cite"] for cite in case["citations"]],
                    "jurisdiction": case["jurisdiction"],
                    "court": case["court"],
                    "first_page": case["first_page"],
                    "last_page": case["last_page"],
                    "file_name": case["file_name"],
                    "name_short": case["name_abbreviation"],
                    "name": case["name"],
                },
            )
        ],
    )
    progress()


@click.command()
def train():
    client = QdrantClient(path="./case-db")

    model = SentenceTransformer("all-MiniLM-L6-v2")

    zips = downloads_dir.glob("*/*.zip")

    # cases_dir.glob("*/json/*.json")
    if client.collection_exists(COLLECTION_NAME):
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
    with alive_bar(unknown="radioactive") as bar:
        for zip_path in zips:
            zip = zipfile.ZipFile(zip_path)
            bar.text = f"{zip_path.parent.name}/{zip_path.stem}"
            for case_file in zipfile.Path(zip, "json/").iterdir():
                # bar.text = f"{zip_path.parent.name}/{zip_path.stem}/{case_file.name}"
                build_db(case_file, client, model, bar)

    query = input("Query: ")
    vecs = model.encode(query)

    hits = client.search(collection_name="cases", query_vector=vecs.tolist(), limit=2)

    print(hits)
