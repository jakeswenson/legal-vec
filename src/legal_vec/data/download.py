import click
import legal_vec
import httpx
from alive_progress import alive_bar
from typing import Iterator
from legal_vec.types import JurisdictionFull, Reporter, ReporterVolume

client = httpx.Client(http2=True, base_url="https://static.case.law")
jurisdiction_files = legal_vec.data_dir.glob("Jurisdiction.*.json")
volumes_file = legal_vec.data_dir / "VolumesMetadata.json"

jurisdictions: list[JurisdictionFull] = [legal_vec.parse_json(f) for f in jurisdiction_files]

reporters: Iterator[Reporter] = (r for j in jurisdictions for r in j["reporters"])

jurisdiction_ids = set(j["id"] for j in jurisdictions)

volumes: Iterator[ReporterVolume] = (
    v
    for v in legal_vec.parse_json_stream(volumes_file)
    for jur in v["jurisdictions"]
    if jur["id"] in jurisdiction_ids
)


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
        total = int(r.headers["Content-Length"])
        bar.text(f"{reporter_slug}/{vol}.zip")
        # dl_progress = progress.add_task(f"[green]...", total=total)
        # with alive_bar(total) as dl_bar:
        with open(dl_path, mode="ab") as output:
            for data in r.iter_bytes():
                output.write(data)
    # progress.advance(dl_progress, len(data))
    # dl_bar(len(data))
    # progress.remove_task(dl_progress)

    dl_path.rename(output_path)
    return True


@click.command()
def main():
    vols: list[ReporterVolume] = list(volumes)

    print(f"Volumes: {len(vols)}")

    # with Progress() as progress:
    #     volumes_progress = progress.add_task("[blue]Volumes...", total=len(vols))

    with alive_bar(len(vols), title="Volume") as vol_bar:
        for vol in vols:
            downloaded = download_volume(vol["reporter_slug"], vol["volume_number"], vol_bar)
            vol_bar(skipped=not downloaded)
            # progress.advance(volumes_progress)
