import os
from pathlib import Path

import utils
from utils import save_pdf


def test_save_pdf_creates_and_writes_file(tmp_path, monkeypatch):
    """
    Writes to <project_root>/downloads/ even when called from anywhere.
    We monkeypatch utils.__file__ so the 'project root' is tmp_path.
    """
    fake_utils_file = tmp_path / "utils.py"
    fake_utils_file.write_text("# fake utils for testing\n")
    monkeypatch.setattr(utils, "__file__", str(fake_utils_file), raising=False)

    pdf_name = "sample"  # intentionally without extension
    pdf_content = b"%PDF-1.4\n%fake content\n"

    saved_path = save_pdf(pdf_name, pdf_content)
    saved_file = Path(saved_path)

    expected_dir = tmp_path / "downloads"
    expected_file = expected_dir / "sample.pdf"

    assert saved_file == expected_file
    assert expected_dir.exists() and expected_dir.is_dir()
    assert saved_file.exists()
    assert saved_file.suffix.lower() == ".pdf"
    assert saved_file.read_bytes() == pdf_content
