import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFPageCountError
from PIL import Image
import numpy as np
import re
import os

POPPLER_PATH = r"C:\poppler\Library\bin"
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def ExtractText_Tesseract(file_path):
    print("Tesseract Extracting...")
    stext = ""
    custom_config = r'-c preserve_interword_spaces=1 --oem 1 --psm 6 -l eng'

    ext = os.path.splitext(file_path)[1].lower()

    text_data = ""

    # ---- CASE 1: PDF ----
    if ext == ".pdf":
        pages = convert_from_path(file_path, poppler_path=POPPLER_PATH)
        print(f"Number of pages extracted: {len(pages)}")

        for i, page in enumerate(pages):
            try:
                text = pytesseract.image_to_string(page, config=custom_config)
                cleaned_page_text = re.sub(r'^\d+\s*', '', text, flags=re.MULTILINE)
                text_data += cleaned_page_text + '\n'
                stext = ' '.join(text_data.split())
            except Exception as e:
                print(f"Error while extracting text from page {i + 1}: {str(e)}")

    # ---- CASE 2: IMAGE (BMP, PNG, JPG, etc.) ----
    else:
        try:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, config=custom_config)
            cleaned_page_text = re.sub(r'^\d+\s*', '', text, flags=re.MULTILINE)
            text_data = cleaned_page_text
            stext = ' '.join(text_data.split())
        except Exception as e:
            print(f"Error while extracting text from image: {str(e)}")

    return text_data


# file_path = r"D:\Projects\TPCPP\Image Samples\2020Ont15279-1-Affidavit of Bruce Arnott_Page_8.tif"
file_path = r"D:\Projects\TPCPP\split pdf\2024NS318-17-Letterhead Factum\page_2.pdf"

text = ExtractText_Tesseract(file_path)

with open("PDF_medium_3.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("Done")
