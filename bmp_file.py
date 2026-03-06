import cv2
import pytesseract
from PIL import Image
import numpy as np

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def ExtractText_From_BMP(image_path):
    print("Preprocessing image...")

    img = cv2.imread(image_path)

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Increase contrast
    gray = cv2.equalizeHist(gray)

    # 3. Adaptive threshold (best for scanned docs)
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 2
    )

    # 4. Remove noise
    kernel = np.ones((1,1), np.uint8)
    clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    custom_config = r'--oem 3 --psm 6 -l eng'
    text = pytesseract.image_to_string(clean, config=custom_config)

    return text


file_path = r"D:\Projects\TPCPP\Image Samples\2024NAT30442.BMP"
text = ExtractText_From_BMP(file_path)

with open("BMP_clean_output.txt", "w", encoding="utf-8") as f:
    f.write(text)

print("Done")
