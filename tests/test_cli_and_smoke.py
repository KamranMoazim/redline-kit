import json
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from redline_kit.cli.main import app
from tests.conftest import CONTRACT_DOCX, EXAMPLES_DIR

RUNNER = CliRunner()


def test_cli_apply_and_mine(tmp_path):
    output = tmp_path / "out.docx"
    applied = RUNNER.invoke(
        app, ["apply", str(CONTRACT_DOCX), str(EXAMPLES_DIR / "edits.json"), "-o", str(output)]
    )
    assert applied.exit_code == 0, applied.output
    assert "7 applied, 1 unmatched" in applied.output

    playbook = tmp_path / "playbook.json"
    mined = RUNNER.invoke(app, ["mine", str(output), "-o", str(playbook)])
    assert mined.exit_code == 0, mined.output
    assert len(json.loads(playbook.read_text())) == 8


def test_cli_rejects_mismatched_output(tmp_path):
    result = RUNNER.invoke(
        app,
        [
            "apply",
            str(CONTRACT_DOCX),
            str(EXAMPLES_DIR / "edits.json"),
            "-o",
            str(tmp_path / "x.pdf"),
        ],
    )
    assert result.exit_code != 0


@pytest.mark.skipif(
    shutil.which("soffice") is None, reason="LibreOffice not installed (runs in Docker)"
)
def test_output_opens_cleanly_in_libreoffice(tmp_path):
    output = tmp_path / "out.docx"
    RUNNER.invoke(
        app, ["apply", str(CONTRACT_DOCX), str(EXAMPLES_DIR / "edits.json"), "-o", str(output)]
    )
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(output)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert (tmp_path / "out.pdf").stat().st_size > 1000
