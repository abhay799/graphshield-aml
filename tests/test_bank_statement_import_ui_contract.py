from pathlib import Path
import subprocess

HTML = Path("ui/portfolio/index.html").read_text(encoding="utf-8")
JS = Path("ui/portfolio/bank-statement-import.js").read_text(encoding="utf-8")


def test_bank_statement_import_surface_present():
    for marker in (
        'id="statement-import"',
        'id="statement-file"',
        'id="statement-analyze"',
        'id="statement-load"',
        'id="statement-preview"',
        'bank-statement-import.js',
        'xlsx.full.min.js',
    ):
        assert marker in HTML


def test_bank_statement_privacy_and_mapping_contract():
    lower = (HTML + JS).lower()
    for phrase in (
        "original statement file is not uploaded",
        "counterparty",
        "hashed",
        "account alias",
        "csv",
        "xlsx",
    ):
        assert phrase in lower
    assert "detectMapping" in JS
    assert "toGraphShieldCSV" in JS
    assert "GraphShieldBatchUI.importCSVText" in JS


def test_bank_statement_js_syntax():
    result = subprocess.run(
        ["node", "--check", "ui/portfolio/bank-statement-import.js"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
