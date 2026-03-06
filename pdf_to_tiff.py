from pdf2image import convert_from_path
from PIL import Image
import os


def pdf_to_tiff(input_pdf, output_tiff, dpi=300):
    """
    Convert a PDF file to a multi-page TIFF.
    
    :param input_pdf: Path to input PDF
    :param output_tiff: Path to output TIFF
    :param dpi: Resolution for conversion (default 300 for OCR quality)
    """

    # Convert PDF pages to PIL Images
    pages = convert_from_path(input_pdf, dpi=dpi)

    if not pages:
        raise ValueError("No pages found in PDF.")

    # Save as multi-page TIFF
    pages[0].save(
        output_tiff,
        save_all=True,
        append_images=pages[1:],
        compression="tiff_lzw"  # Good compression for OCR workflows
    )

    print(f"TIFF saved at: {output_tiff}")


# Example usage
pdf_to_tiff("input.pdf", "output.tiff")