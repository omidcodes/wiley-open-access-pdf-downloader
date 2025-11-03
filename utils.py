import os
import hashlib

directory_name = "downloads"
project_root = os.path.dirname(os.path.abspath(__file__))  # e.g., .../wiley-open-access-pdf-downloader
directory_path = os.path.join(project_root, directory_name)


def save_pdf(pdf_name: str, pdf_content: bytes, directory_path=directory_path) -> str:
    """
    Saves a PDF file (bytes) to the 'downloads/' directory in the project root.

    :param pdf_name: Name of the PDF file (e.g. "paper.pdf" or "10.1002_xyz.pdf")
    :param pdf_content: PDF bytes content
    :return: Full file path of the saved PDF (relative to project root)
    """

    # Get absolute path of project root (where this file's parent folder is)
    project_root = os.path.dirname(os.path.abspath(__file__))  # e.g., .../wiley-open-access-pdf-downloader
    downloads_dir = os.path.join(project_root, directory_name)

    # Make sure 'downloads/' exists
    os.makedirs(downloads_dir, exist_ok=True)

    # Ensure .pdf extension
    if not pdf_name.lower().endswith(".pdf"):
        pdf_name += ".pdf"

    # Full path to save file
    full_path = os.path.join(downloads_dir, pdf_name)

    # Write file
    with open(full_path, "wb") as f:
        f.write(pdf_content)

    print(f"[LOCAL : PDF saved] {full_path} | size={len(pdf_content)} bytes")
    return full_path

def hashify(input):
    in_bytes = input.encode('utf-8') 
    hash_object = hashlib.sha256(in_bytes)
    # Get the hexadecimal representation of the hash
    password_hash = hash_object.hexdigest()
    

    return password_hash