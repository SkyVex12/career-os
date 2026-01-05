import subprocess
import tempfile
import os


def docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        docx_path = os.path.join(tmp, "resume.docx")
        pdf_path = os.path.join(tmp, "resume.pdf")

        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                tmp,
                docx_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        with open(pdf_path, "rb") as f:
            return f.read()
