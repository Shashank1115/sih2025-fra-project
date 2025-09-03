# ai_models/digitization.py
from PIL import Image
import pytesseract
import re

# Point to installed Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_info_from_image(image_path):
    """Extract claim data from a document image using OCR + regex."""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)

        # Debug: Show raw OCR output
        print("\n================ OCR RAW TEXT ================")
        print(text)
        print("=============================================\n")

        data = {
            "patta_holder": "Unknown",
            "village": "Unknown",
            "coordinates": "Unknown",
            "claim_status": "Unknown"
        }

        # --- Parse fields ---
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            if "Name:" in line:
                data["patta_holder"] = line.split("Name:")[1].strip()
            elif "Village:" in line:
                data["village"] = line.split("Village:")[1].strip()
            elif "Status:" in line:
                data["claim_status"] = line.split("Status:")[1].strip()

        # --- Extract coordinates anywhere in text ---
        match = re.search(r"(\d+\.\d+)\s*[, ]\s*(\d+\.\d+)", text)
        if match:
            data["coordinates"] = f"{match.group(1)},{match.group(2)}"

        # --- Fail if coords not found ---
        if data["coordinates"] == "Unknown":
            raise ValueError("⚠️ No coordinates detected in OCR text.")

        print(f"✅ Parsed Data: {data}")
        return data

    except Exception as e:
        print(f"❌ OCR extraction failed: {e}")
        return None
