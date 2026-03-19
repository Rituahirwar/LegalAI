from sqlalchemy.orm import Session
from sentence_transformers import SentenceTransformer
from .models import LegalDocument
import os

print("🤖 Loading Embedding Model (all-mpnet-base-v2) for Search...")
# Ensure we load the same model used in generate_embeddings.py
model = SentenceTransformer('all-mpnet-base-v2')
print("✅ Embedding Model Loaded!")

def hybrid_search(db: Session, query: str, top_k: int = 4):
    """
    Retrieves the most relevant legal documents for a given query.
    Currently uses semantic vector search using pgvector.
    """
    try:
        # 1. Convert the user's text query into a 768-dimension vector
        query_embedding = model.encode(query).tolist()
        
        # 2. Query the database using pgvector's cosine distance
        # We fetch the document and the actual distance score
        results = db.query(
            LegalDocument,
            LegalDocument.embedding.cosine_distance(query_embedding).label("distance")
        ).order_by("distance").limit(top_k).all()
        
        # 3. Format the results for the frontend/LLM to consume
        formatted_results = []
        for doc, distance in results:
            # Cosine distance: 0 means identical, 2 means exactly opposite. 
            # We convert distance to a similarity score (1 - distance)
            score = 1.0 - (distance if distance is not None else 0.0)
            
            formatted_results.append({
                "content": doc.rag_text,
                "act_name": doc.act_name,
                "section": doc.section_number,
                "title": doc.section_title,
                "score": score
            })
            
        return formatted_results

    except Exception as e:
        print(f"❌ Error during search: {str(e)}")
        # The main app expects a dict with an 'error' key if it fails
        return {"error": str(e)}
