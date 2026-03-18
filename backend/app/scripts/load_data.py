import os
import json
from sqlalchemy.orm import Session
from sqlalchemy import text # <--- Added text import here
import sys

# Setup paths
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(backend_dir)

from app.database import SessionLocal
from app.models import LegalDocument

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(CURRENT_DIR, "data", "raw")

def extract_all_sections(data, current_chapter="Unknown"):
    """
    Recursively digs through ANY JSON structure to find legal sections.
    It looks for keys like 'description', 'desc', or 'text'.
    """
    sections = []
    
    if isinstance(data, list):
        for item in data:
            sections.extend(extract_all_sections(item, current_chapter))
            
    elif isinstance(data, dict):
        # Try to catch chapter names if they exist at this level
        chap = str(data.get('chapter', data.get('chapter_title', current_chapter)))
        
        # Check if this dictionary IS a legal section (does it have a description/text?)
        desc = str(data.get('description', data.get('desc', data.get('section_desc', data.get('text', ''))))).strip()
        
        if desc and desc.lower() != 'none':
            # We found a section! Let's grab its number and title
            sec_num = str(data.get('number', data.get('section', data.get('Section', data.get('id', ''))))).strip()
            title = str(data.get('title', data.get('section_title', data.get('heading', '')))).strip()
            
            sections.append({
                "chapter": chap,
                "section": sec_num,
                "title": title,
                "description": desc
            })
            
        # Keep digging deeper into the JSON just in case there are nested sections
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                sections.extend(extract_all_sections(value, chap))
                
    return sections

def process_and_load_json(filepath: str, db: Session):
    filename = os.path.basename(filepath)
    act_name = filename.replace('.json', '').upper() 
    
    print(f"\n📥 Digging into {act_name}...")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # --- HANDLE THE BROKEN HMA.JSON/IDA.JSON FORMAT ---
        if isinstance(data, list) and len(data) > 0 and "chapter,section,section_title,section_desc" in data[0]:
            print(f"⚠️ Detected broken CSV-in-JSON format for {act_name}. Parsing manually...")
            records_inserted = 0
            last_sec_num = "Unknown"
            last_title = "Unknown"
            
            for item in data:
                val = item.get("chapter,section,section_title,section_desc", "")
                if not val.strip(): continue
                
                parts = val.split(',', 3)
                if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
                    last_sec_num = parts[1].strip()
                    last_title = parts[2].strip().strip('"')
                    desc = parts[3].strip().strip('"')
                else:
                    desc = val.strip().strip('"')

                full_rag_text = f"Law/Act: {act_name}\nSection: {last_sec_num}\nTitle: {last_title}\nContent: {desc}"
                db.add(LegalDocument(act_name=act_name, section_number=last_sec_num, section_title=last_title, rag_text=full_rag_text))
                records_inserted += 1
                if records_inserted % 100 == 0: db.commit()
            
            db.commit()
            print(f"✅ Successfully loaded {records_inserted} sections for {act_name}!")
            return

        # Run the universal extractor for properly formatted JSONs
        extracted_sections = extract_all_sections(data)

        if not extracted_sections:
            print(f"⚠️ Warning: Could not find any descriptions/text in {filename}.")
            return

        records_inserted = 0

        for sec in extracted_sections:
            full_rag_text = (
                f"Law/Act: {act_name}\n"
                f"Chapter: {sec['chapter']}\n"
                f"Section: {sec['section']}\n"
                f"Title: {sec['title']}\n"
                f"Content: {sec['description']}"
            )
            
            db_record = LegalDocument(
                act_name=act_name,
                section_number=sec['section'],
                section_title=sec['title'],
                rag_text=full_rag_text
            )
            
            db.add(db_record)
            records_inserted += 1

            if records_inserted % 100 == 0:
                db.commit()

        db.commit()
        print(f"✅ Successfully extracted and loaded {records_inserted} sections for {act_name}!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error loading {filename}: {str(e)}")

def main():
    if not os.path.exists(JSON_DIR):
        print(f"❌ Error: Directory not found: {JSON_DIR}")
        return

    print(f"🚀 Starting Universal JSON Ingestion...")
    db = SessionLocal()
    
    try:
        # Wrapped in text() for SQLAlchemy 2.0+
        db.execute(text("TRUNCATE TABLE legal_documents RESTART IDENTITY;"))
        db.commit()
        print("🧹 Cleaned old database entries...")

        json_files = [f for f in os.listdir(JSON_DIR) if f.endswith('.json')]
        for file in json_files:
            process_and_load_json(os.path.join(JSON_DIR, file), db)
            
        print("\n🎉 ALL JSON LAWS LOADED SUCCESSFULLY!")
    finally:
        db.close()

if __name__ == "__main__":
    main()