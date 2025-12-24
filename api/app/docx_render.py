from docxtpl import DocxTemplate
from pathlib import Path

TPL_DIR = Path(__file__).resolve().parent / "templates"

def render_resume(context: dict) -> bytes:
    tpl = DocxTemplate(str(TPL_DIR / "resume_template.docx"))
    tpl.render(context)
    out = TPL_DIR / "_out_resume.docx"
    tpl.save(out)
    return out.read_bytes()
