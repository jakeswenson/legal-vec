import json
from pathlib import Path

from typing import TypedDict
from collections.abc import Iterator
import json_stream

from legal_vec.types import Opinion, CaseMetadata

my_dir = Path(__file__).parent
data_dir = (my_dir / "../../data/").resolve()
cases_dir = data_dir / "cases"
downloads_dir = data_dir / "downloads"
case_metadata_files = [m for m in cases_dir.glob("*/metadata/CasesMetadata.json")]


def parse_json[T: TypedDict](path: Path) -> T:
    with path.open(mode="r") as file:
        return json.load(file)


def parse_json_stream[T: TypedDict](path: Path) -> Iterator[T]:
    return json_stream.load(open(path), persistent=True)
