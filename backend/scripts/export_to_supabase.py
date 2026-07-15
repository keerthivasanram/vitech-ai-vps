import os
import json
import sys
from pathlib import Path
from supabase import create_client, Client

# Ensure we can import the app module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store import get_collection

# Hardcoded for demonstration
SUPABASE_URL = "https://qtwmcfqyrhlxcqkaedet.supabase.co"
SUPABASE_KEY = "sb_publishable_RHsXGWcgyL0qxKdz2KsGSQ_iOGqT6a-"

def export_to_supabase():
    print("Connecting to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Reading data from local ChromaDB...")
    try:
        col = get_collection()
        count = col.count()
    except Exception as e:
        print(f"Error accessing ChromaDB: {e}")
        return

    if count == 0:
        print("No documents found in ChromaDB.")
        return
        
    print(f"Found {count} documents. Fetching...")
    res = col.get(include=["metadatas"])
    
    records_to_insert = []
    
    for m in res["metadatas"]:
        raw = m.get("_raw")
        if not raw:
            continue
            
        record = json.loads(raw)
        
        # Parse nested data safely
        price_schedule = record.get("price_schedule", {})
        
        # Map to the new advanced relational schema
        row = {
            "id": str(record.get("id")),
            "category": str(record.get("category", "")),
            "title": str(record.get("title", "")),
            "client_name": str(record.get("client", "")),
            "vendor_name": str(record.get("vendor", "")),
            "reference_no": str(record.get("ref", "")),
            "quotation_date": str(record.get("date", "2023-01-01")), # Default fallback for date
            "source_file": str(record.get("source_file", "")),
            "grand_total": price_schedule.get("grand_total", 0),
            "final_price": price_schedule.get("final_price", 0),
            "currency": str(price_schedule.get("currency", "INR")),
            "given_requirements": record.get("given_data", {}),
            "technical_specifications": record.get("technical_details", {})
        }
        records_to_insert.append(row)

    print(f"Prepared {len(records_to_insert)} structured records for insertion.")
    
    # Insert in batches
    batch_size = 50
    inserted = 0
    for i in range(0, len(records_to_insert), batch_size):
        batch = records_to_insert[i:i+batch_size]
        try:
            # Upsert into the new highly-structured table
            response = supabase.table("processed_quotations").upsert(batch).execute()
            inserted += len(response.data)
            print(f"Inserted/Upserted batch {i//batch_size + 1}... ({inserted}/{len(records_to_insert)})")
        except Exception as e:
            print(f"Error inserting batch: {e}")
            
    print("Advanced Export complete!")

if __name__ == "__main__":
    export_to_supabase()
