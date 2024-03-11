import click
import rich

import legal_vec
import httpx
from alive_progress import alive_bar
from typing import Iterator
from pathlib import Path
from legal_vec.types import JurisdictionFull, Reporter, ReporterVolume

client = httpx.Client(http2=True, base_url="https://static.case.law")
volumes_file = legal_vec.data_dir / "VolumesMetadata.json"
jurisdictions_file = legal_vec.data_dir / "JurisdictionsMetadata.json"


def download_volume(reporter_slug: str, vol: str, bar) -> bool:
    output_path = legal_vec.downloads_dir / f"{reporter_slug}/{vol}.zip"
    dl_path = legal_vec.downloads_dir / f"{reporter_slug}/{vol}.zip.dl"

    if output_path.exists():
        return False

    downloaded = dl_path.stat().st_size - 1 if dl_path.exists() else 0

    output_path.parent.mkdir(exist_ok=True)
    headers = {"Range": f"bytes={downloaded}-"}
    url: str = f"/{reporter_slug}/{vol}.zip"
    with client.stream("GET", url=url, headers=headers) as r:
        r.raise_for_status()

        count = downloaded
        total = int(r.headers["Content-Length"])
        with open(dl_path, mode="ab") as output:
            for data in r.iter_bytes():
                bar.text(f"{reporter_slug}/{vol}.zip {count}/{total} ")
                output.write(data)
                count += len(data)

    dl_path.rename(output_path)
    return True


def download_json_file(file: Path):
    dl_path = volumes_file.with_suffix(".json.dl")

    with client.stream("GET", url=file.name) as r:
        response: httpx.Response = r
        rich.print(f"[red]{response.status_code} [blue]{response.url}")
        rich.print(f"[yellow]Headers: {response.headers}")
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", -1))
        with alive_bar(total if total > 0 else None) as bar:
            with dl_path.open(mode="wb") as output:
                for data in r.iter_bytes():
                    output.write(data)
                    bar(len(data))

    dl_path.rename(file)


def download_volumes_file():
    rich.print("[green] Downloading volumes file...")
    download_json_file(volumes_file)


def download_jurisdictions():
    rich.print("[green] Downloading volumes file...")
    download_json_file(jurisdictions_file)


@click.command()
def main():
    if not volumes_file.exists():
        download_volumes_file()

    jurisdiction_files = list(legal_vec.data_dir.glob("Jurisdiction.*.json"))

    if not jurisdiction_files:
        download_jurisdictions()

    jurisdictions_of_interest = {"Cal.", "U.S."}

    # jurisdictions: list[JurisdictionFull] = [legal_vec.parse_json(f) for f in jurisdiction_files]
    # jurisdiction_ids = set(j["id"] for j in jurisdictions)

    rich.print(f"[green]Finding volumes in jurisdictions: {jurisdictions_of_interest}")

    volumes: Iterator[ReporterVolume] = (
        v
        for v in legal_vec.parse_json_stream(volumes_file)
        for jur in v["jurisdictions"]
        if jur["name"] in jurisdictions_of_interest
    )

    vols: list[ReporterVolume] = list(volumes)

    rich.print(f"[blue]volumes: {len(vols)}")

    already_downloaded = 0

    with alive_bar(len(vols), title="Volume") as vol_bar:
        for vol in vols:
            downloaded = download_volume(vol["reporter_slug"], vol["volume_number"], vol_bar)
            vol_bar(skipped=not downloaded)
            if not downloaded:
                already_downloaded += 1

    rich.print(f"[purple](skipped: {already_downloaded})")
