import os
import re
from sqlalchemy.orm import Session
from sqlalchemy import text # <--- Added text import here
import sys

# Setup paths to ensure we can import 'app'
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(backend_dir)

from app.database import SessionLocal
from app.models import LegalDocument

# Point exactly to your BNS file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Note: Changing this to point to the exact path shown in your error
FILE_PATH = os.path.join(CURRENT_DIR, "data", "processed", "bns_clean.csv") 

def load_bns_raw_text(filepath: str, db: Session):
    if not os.path.exists(filepath):
        print(f"❌ Error: File not found at {filepath}")
        return

    print(f"📥 Reading BNS raw text from {filepath}...")
    
    try:
        # Read the entire file as a single giant string (ignoring commas)
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_text = f.read()

        # Regex Magic: This splits the giant text every time it sees "Section 1:", "Section 105A:", etc.
        # It creates a list where [1] is the Section Number, and [2] is the text for it.
        chunks = re.split(r'(Section \d+[a-zA-Z]*:)', raw_text)
        
        records_inserted = 0
        
        # We start at index 1 and jump by 2 because:
        # chunks[1] = "Section 1:"
        # chunks[2] = "Short title, commencement... (1) This Act..."
        for i in range(1, len(chunks) - 1, 2):
            sec_header = chunks[i].strip()      # e.g., "Section 1:"
            sec_content = chunks[i+1].strip()   # e.g., "Short title, commencement. (1) This Act..."
            
            # Clean up the Section Number (Remove "Section" and ":")
            sec_num = sec_header.replace("Section", "").replace(":", "").strip()
            
            # Split the Title from the Description using the first period "."
            if "." in sec_content:
                parts = sec_content.split(".", 1)
                sec_title = parts[0].strip() # "Short title, commencement and application"
                content = parts[1].strip()   # "(1) This Act may be called..."
            else:
                sec_title = sec_content
                content = ""
            
            # --- Format for the AI ---
            full_rag_text = (
                f"Law/Act: BNS\n"
                f"Chapter: Unknown\n"
                f"Section: {sec_num}\n"
                f"Title: {sec_title}\n"
                f"Content: {content}"
            )
            
            # Insert into database
            db_record = LegalDocument(
                act_name="BNS",
                section_number=sec_num,
                section_title=sec_title,
                rag_text=full_rag_text
            )
            
            db.add(db_record)
            records_inserted += 1

            if records_inserted % 100 == 0:
                db.commit()

        # Commit any remaining rows
        db.commit()
        print(f"✅ Successfully extracted and loaded {records_inserted} BNS sections into Supabase!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error loading BNS: {str(e)}")

def main():
    print("🚀 Starting BNS Text Extraction...")
    db = SessionLocal()
    try:
        # Optional: Delete old BNS records so we don't get duplicates if you run it twice
        db.execute(text("DELETE FROM legal_documents WHERE act_name = 'BNS';"))
        db.commit()
        
        load_bns_raw_text(FILE_PATH, db)
    finally:
        db.close()

if __name__ == "__main__":
    main()