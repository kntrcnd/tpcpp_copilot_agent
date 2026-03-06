from PyPDF2 import PdfReader, PdfWriter
from pathlib import Path

# Define paths properly (do NOT hardcode strings inside the function)
INPUT_DIR = Path(r"D:\Projects\TPCPP\PDF samples")
OUTPUT_BASE_DIR = Path(r"D:\Projects\TPCPP\split pdf")

def split_pdf(input_pdf):
    input_pdf = Path(input_pdf)
    reader = PdfReader(input_pdf)

    # Create: D:\Projects\TPCPP\split pdf\<filename>\
    output_dir = OUTPUT_BASE_DIR / input_pdf.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)

        output_path = output_dir / f"page_{i}.pdf"
        with open(output_path, "wb") as f:
            writer.write(f)

    print(f"Split complete! {len(reader.pages)} pages created in:")
    print(output_dir)


# Optional: automatically process ALL PDFs inside the input folder
if __name__ == "__main__":
    for pdf_file in INPUT_DIR.glob("*.pdf"):
        split_pdf(pdf_file)