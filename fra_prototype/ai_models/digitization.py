# ai_models/digitization.py
from PIL import Image
import pytesseract

# --- IMPORTANT FIX ---
# This line manually tells the script where to find the Tesseract program.
# Please double-check this path on your computer. It should be the path
# to the 'tesseract.exe' file you found after installing the program.
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# --- END OF FIX ---

def extract_info_from_image(image_path):
    """Uses OCR and simple text processing to extract data from a document image."""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)

        # Placeholder NER logic using simple string splitting
        lines = text.split('\n')
        data = {
            "patta_holder": "Unknown",
            "village": "Unknown",
            "coordinates": "Unknown",
            "claim_status": "Unknown"
        }
        for line in lines:
            if "Name:" in line:
                data["patta_holder"] = line.split("Name:")[1].strip()
            if "Village:" in line:
                data["village"] = line.split("Village:")[1].strip()
            if "Coords:" in line:
                data["coordinates"] = line.split("Coords:")[1].strip()
            if "Status:" in line:
                data["claim_status"] = line.split("Status:")[1].strip()
        
        return data
    except FileNotFoundError:
        print(f"Error: The image file was not found at {image_path}")
        return None
    except Exception as e:
        print(f"An error occurred while processing the document: {e}")
        return None