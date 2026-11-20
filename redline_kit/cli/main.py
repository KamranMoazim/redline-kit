import json
import logging
from pathlib import Path

import typer
from pydantic import TypeAdapter

from redline_kit.core.models import Edit, MinedEdit, RedlineResult
from redline_kit.parsers.docx_miner import mine_docx
from redline_kit.parsers.pdf_miner import mine_pdf
from redline_kit.writers.docx_track import DEFAULT_AUTHOR, redline_docx
from redline_kit.writers.pdf_redline import redline_pdf

app = typer.Typer(
    help="Native Word Track Changes, PDF redlines, and a redline miner.", no_args_is_help=True
)

EDITS_ADAPTER = TypeAdapter(list[Edit])
MINED_ADAPTER = TypeAdapter(list[MinedEdit])


def load_edits(path: Path) -> list[Edit]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return EDITS_ADAPTER.validate_python(payload["edits"] if isinstance(payload, dict) else payload)


def _suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in (".docx", ".pdf"):
        raise typer.BadParameter(f"Unsupported file type: {path.name} (use .docx or .pdf)")
    return suffix


def _report(result: RedlineResult) -> None:
    for outcome in result.outcomes:
        detail = outcome.location if outcome.status == "applied" else outcome.reason
        method = f" {outcome.method}" if outcome.method == "fuzzy" else ""
        typer.echo(f"  [{outcome.status}{method}] {outcome.edit.find!r} -> {detail}")
    typer.echo(f"{len(result.applied)} applied, {len(result.unmatched)} unmatched")


@app.command()
def apply(
    document: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Contract .docx or .pdf"
    ),
    edits: Path = typer.Argument(..., exists=True, dir_okay=False, help="JSON list of edits"),
    output: Path = typer.Option(..., "--output", "-o", help="Where to write the redlined file"),
    author: str = typer.Option(DEFAULT_AUTHOR, help="Revision and comment author"),
) -> None:
    """Apply edits as Track Changes (.docx) or strikeouts and notes (.pdf)."""
    suffix = _suffix(document)
    if output.suffix.lower() != suffix:
        raise typer.BadParameter(f"Output must also be {suffix}")
    writer = redline_docx if suffix == ".docx" else redline_pdf
    _report(writer(document, load_edits(edits), output, author=author))


@app.command()
def mine(
    document: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Marked-up .docx or .pdf"
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="JSON output (default stdout)"),
) -> None:
    """Read tracked changes, comments and annotations back out as JSON."""
    miner = mine_docx if _suffix(document) == ".docx" else mine_pdf
    payload = MINED_ADAPTER.dump_json(miner(document), indent=2, exclude_none=True).decode()
    if output is None:
        typer.echo(payload)
    else:
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"Wrote {output}")


@app.callback()
def configure_logging(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )


if __name__ == "__main__":
    app()
