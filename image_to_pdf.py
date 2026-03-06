from PIL import Image
import os

input_path = r"D:\Projects\TPCPP\Image Samples\2024NAT30442.BMP"
output_path = r"D:\Projects\TPCPP\output\2024NAT30442.pdf"

img = Image.open(input_path)
img = img.convert("RGB")  # PDF requires RGB
img.save(output_path)

print("Saved:", output_path)