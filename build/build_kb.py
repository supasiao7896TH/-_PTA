"""One-time preprocessing script: extract text + base64-encode PDFs into pta-repo/index.html.

Run manually whenever the source PDFs or build/template.html change:
    pip install -r build/requirements.txt
    python build/build_kb.py

Not part of the shipped app - the generated index.html has no runtime dependency on this script.
"""
import base64
import json
import re
from pathlib import Path

from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BUILD_DIR / "template.html"
OUTPUT_PATH = REPO_ROOT / "index.html"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 50

# Hand-written metadata for the 9 known documents.
DOCS = [
    {
        "id": "alarm_list",
        "file": "ALARM_LIST_FOR_DCS_ANNUNCATING_LAMPS_A_RANK_AND_B_RANK_ALARM_REV_1 (1).pdf",
        "title": "รายการอาลาร์ม DCS (A/B Rank)",
        "desc": "รายการอาลาร์มของหลอดสัญญาณ DCS แยกตาม A-Rank และ B-Rank สำหรับหน่วย TA และ PTA พร้อมตาราง tag และผังหน้าปัดอาลาร์ม",
    },
    {
        "id": "exapilot_training",
        "file": "Exapilot Training  (Full) (2).pdf",
        "title": "คู่มืออบรม Exapilot",
        "desc": "เอกสารอบรมการใช้งาน Exapilot (ซอฟต์แวร์ทำ SOP อัตโนมัติของ Yokogawa) ครอบคลุมแนวคิด, การสร้าง flowchart, และการปฏิบัติจริง",
    },
    {
        "id": "abbreviations_symbols",
        "file": "MIS-04003 ABBREVIATIONS AND SYMBOLS FOR PFD AND P & ID.pdf",
        "title": "สัญลักษณ์และตัวย่อสำหรับ PFD/P&ID",
        "desc": "มาตรฐานสัญลักษณ์อุปกรณ์ เส้นท่อ และการกำหนดหมายเลข tag ที่ใช้ในแบบ PFD และ P&ID ของโรงงาน",
    },
    {
        "id": "esd_procedure",
        "file": "MPS_07002_OPERATION_MANUAL_PTA_UNIT_4_EMERGENCY_SHUTDOWN_PROCEDURE.pdf",
        "title": "คู่มือฉุกเฉิน PTA Unit 4 (ESD)",
        "desc": "ขั้นตอนการหยุดเดินเครื่องฉุกเฉิน (Emergency Shutdown) ของหน่วย PTA เมื่อไฟฟ้าดับหรือระบบสาธารณูปโภคขัดข้อง พร้อมขั้นตอนเริ่มเดินเครื่องใหม่",
    },
    {
        "id": "process_parameters",
        "file": "MPS_07012_CONTROL_ON_PROCESS_PARAMETERS_AND_COUNTERMEASURES_AGAINST_PROCESS_DEVIATION_PTA_UNIT.pdf",
        "title": "ค่าพารามิเตอร์กระบวนการและมาตรการแก้ไข",
        "desc": "ตารางค่าปกติ/ค่าที่ยอมรับได้/ค่าวิกฤตของอุปกรณ์หลักในหน่วย PTA 64 รายการ พร้อมวิธีตรวจจับและการแก้ไขเมื่อค่าผิดปกติ",
    },
    {
        "id": "pace_training",
        "file": "PACE for GC-M PTA Project.pdf",
        "title": "คู่มือ PACE (Advanced Process Control)",
        "desc": "เอกสารอบรมการใช้งานหน้าจอ PACE ของ Yokogawa สำหรับควบคุมกระบวนการขั้นสูง (APC) ของโรงงาน",
    },
    {
        "id": "pta_interlock",
        "file": "PTA INTERLOCK (1).pdf",
        "title": "Interlock หน่วย PTA",
        "desc": "รายการ interlock ด้านความปลอดภัยของหน่วย PTA (SD-2xxx) อธิบายเงื่อนไขที่ทำให้ทำงานและการป้องกันอัตโนมัติ",
    },
    {
        "id": "process_description",
        "file": "PTA Process Description 2004.pdf",
        "title": "รายละเอียดกระบวนการผลิต PTA (2004)",
        "desc": "เอกสารอธิบายกระบวนการผลิตอย่างละเอียด ครอบคลุมปฏิกิริยาเคมี หน่วย TA และหน่วย PTA ระบบแยก/อบแห้ง และระบบสาธารณูปโภค",
    },
    {
        "id": "ta_interlock",
        "file": "SMPC_PLANT_INTERLOCK_TA_UNIT.pdf",
        "title": "Interlock หน่วย TA",
        "desc": "รายการ interlock ด้านความปลอดภัยของหน่วย TA (SD-1xxx) อธิบายเงื่อนไขที่ทำให้ทำงานและการป้องกันอัตโนมัติ",
    },
]


def clean_text(text: str) -> str:
    text = text.replace("\x0c", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(para) > size:
                start = 0
                while start < len(para):
                    end = start + size
                    chunks.append(para[start:end])
                    start = end - overlap
                buf = ""
            else:
                buf = para
    if buf:
        chunks.append(buf)
    return chunks


def extract_chunks(doc_id: str, pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    result = []
    for page_num, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        text = clean_text(raw)
        if not text:
            continue
        for chunk in chunk_text(text):
            if chunk.strip():
                result.append({"doc": doc_id, "page": page_num, "text": chunk})
    return result


def encode_pdf(pdf_path: Path) -> str:
    return base64.b64encode(pdf_path.read_bytes()).decode("ascii")


def main():
    all_chunks = []
    pdf_b64 = {}
    print("Extracting text and encoding PDFs...")
    for doc in DOCS:
        pdf_path = REPO_ROOT / doc["file"]
        if not pdf_path.exists():
            raise FileNotFoundError(f"Missing PDF: {pdf_path}")
        chunks = extract_chunks(doc["id"], pdf_path)
        all_chunks.extend(chunks)
        pdf_b64[doc["id"]] = encode_pdf(pdf_path)
        size_mb = pdf_path.stat().st_size / (1024 * 1024)
        print(f"  {doc['id']:22s} chunks={len(chunks):5d}  size={size_mb:6.2f}MB  file={doc['file']}")
        if len(chunks) == 0:
            print(f"  WARNING: {doc['id']} produced 0 chunks (possibly scanned/image-only pages)")

    kb_data = {"docs": DOCS, "chunks": all_chunks}

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    output = template.replace(
        "/*__KB_DATA__*/", json.dumps(kb_data, ensure_ascii=False)
    ).replace(
        "/*__KB_PDFS__*/", json.dumps(pdf_b64, ensure_ascii=False)
    )

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\nWrote {OUTPUT_PATH} ({size_mb:.2f}MB), total chunks={len(all_chunks)}")


if __name__ == "__main__":
    main()
