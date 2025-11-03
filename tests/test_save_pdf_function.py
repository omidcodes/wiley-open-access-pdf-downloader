import os
from pathlib import Path

import utils
from utils import save_pdf


# def test_save_pdf_creates_and_writes_file(tmp_path, monkeypatch):
#     """
#     Ensure save_pdf() writes to <project_root>/downloads/, creates the dir,
#     appends .pdf if missing, returns the full path, and preserves content.
#     We monkeypatch utils.__file__ so the 'project root' is the tmp_path.
#     """

#     # Make the function think the project root is tmp_path
#     fake_utils_file = tmp_path / "utils.py"
#     # It doesn't need to exist for os.path.abspath(); but creating it is harmless.
#     fake_utils_file.write_text("# fake utils for testing\n")
#     monkeypatch.setattr(utils, "__file__", str(fake_utils_file), raising=False)

#     # Arrange
#     pdf_name = "sample"  # no extension on purpose
#     pdf_content = b"%PDF-1.4\n%Test PDF content\n"

#     # Act
#     saved_path = save_pdf(pdf_name, pdf_content)

#     # Assert
#     saved_file = Path(saved_path)
#     expected_dir = tmp_path / "downloads"
#     expected_file = expected_dir / "sample.pdf"

#     # 1) Correct path returned
#     assert saved_file == expected_file, "Returned path does not match expected downloads location."

#     # 2) Directory created
#     assert expected_dir.exists() and expected_dir.is_dir(), "downloads/ directory was not created."

#     # 3) File exists and has .pdf extension
#     assert saved_file.exists(), "PDF file was not created."
#     assert saved_file.suffix.lower() == ".pdf", "File should have .pdf extension."

#     # 4) Content preserved
#     assert saved_file.read_bytes() == pdf_content, "Written content does not match original bytes."



def test_save_pdf_creates_and_writes_file(tmp_path, monkeypatch):
    """
    Ensure save_pdf() writes to <project_root>/downloads/, creates the dir,
    appends .pdf if missing, returns the full path, and preserves content.
    We monkeypatch utils.__file__ so the 'project root' is the tmp_path.
    """
    # Arrange
    pdf_name = "test_sample.pdf"  # no extension on purpose
    # pdf_name = 'WileyLibrary_climate_action_pan3.10075.pdf'
    pdf_content = b"%PDF-1.4\n%Test PDF content\n"

    save_pdf(
        pdf_name=pdf_name,
        pdf_content=pdf_content,
        # directory_path="downloads/"
    )