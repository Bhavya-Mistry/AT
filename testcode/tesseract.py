from PIL import Image
import pytesseract

# Explicitly point to the tesseract.exe in your AppData folder
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\bhavya.mistry\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

# Define the path to your image file
image_path = r'C:\Users\bhavya.mistry\Documents\GitHub\AT\media\images1.jpg'

# Open the image using Pillow (PIL)
image = Image.open(image_path)

# Use pytesseract to extract text from the image
text = pytesseract.image_to_string(image)

# Print the extracted text
print("--- Extracted Text ---")
print(text)