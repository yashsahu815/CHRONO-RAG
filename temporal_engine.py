import math
import chromadb
from sentence_transformers import SentenceTransformer

# 1. Initialize local embedding model and in-memory ChromaDB
print("Loading embedding model (all-MiniLM-L6-v2)...")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

client = chromadb.Client()
collection = client.create_collection(
    name="company_policies",
    metadata={"hnsw:space": "cosine"}
)

# 2. Sample multi-version documents with temporal metadata
documents = [
    {
        "id": "policy_2022",
        "text": "The standard remote work policy allows employees up to 2 days of remote work per week. Full remote is strictly disallowed without VP approval.",
        "date": "2022-01-15",
        "year": 2022
    },
    {
        "id": "policy_2024",
        "text": "Updated remote work policy: Employees can work remotely up to 3 days per week with manager sign-off.",
        "date": "2024-06-01",
        "year": 2024
    },
    {
        "id": "policy_2026",
        "text": "Current official remote work directive: All teams operate under a flexible hybrid model with mandatory 1 day in-office and 4 days remote.",
        "date": "2026-02-10",
        "year": 2026
    }
]

# 3. Embed and index documents
texts = [doc["text"] for doc in documents]
embeddings = embedder.encode(texts).tolist()

for doc, emb in zip(documents, embeddings):
    collection.add(
        ids=[doc["id"]],
        embeddings=[emb],
        documents=[doc["text"]],
        metadatas=[{"date": doc["date"], "year": doc["year"]}]
    )

print(f"Indexed {len(documents)} document versions successfully.\n")

# 4. Temporal Decay Scoring Function
def retrieve_and_rank(query: str, target_year: int = 2026, decay_lambda: float = 0.35, top_k: int = 3):
    query_emb = embedder.encode([query]).tolist()[0]
    
    results = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    ranked_chunks = []
    for doc_id, text, meta, dist in zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        cosine_sim = max(0.0, 1.0 - dist)
        doc_year = meta["year"]
        
        # Exponential decay penalty
        delta_years = abs(target_year - doc_year)
        decay_factor = math.exp(-decay_lambda * delta_years)
        final_score = cosine_sim * decay_factor
        
        ranked_chunks.append({
            "id": doc_id,
            "year": doc_year,
            "text": text,
            "cosine_sim": cosine_sim,
            "decay_factor": decay_factor,
            "final_score": final_score
        })
        
    return ranked_chunks

# 5. Run Comparison: Standard RAG (lambda = 0.0) vs. ChronoRAG (lambda = 0.35)
query = "What is the official remote work limit and how many days can I work from home?"
target_year = 2026

print(f"Query: \"{query}\"")
print(f"Target Year: {target_year}\n" + "="*70)

# Standard RAG: lambda = 0 (Time-agnostic)
standard_results = sorted(
    retrieve_and_rank(query, target_year=target_year, decay_lambda=0.0),
    key=lambda x: x["cosine_sim"],
    reverse=True
)

print("\n>>> [STANDARD RAG] Top Results (Static Cosine Similarity):")
for rank, item in enumerate(standard_results, 1):
    print(f"  Rank {rank}: [{item['id']} | Year: {item['year']}] Cosine Sim: {item['cosine_sim']:.4f}")
    print(f"         \"{item['text'][:85]}...\"")

# ChronoRAG: lambda = 0.35 (Time-calibrated)
chrono_results = sorted(
    retrieve_and_rank(query, target_year=target_year, decay_lambda=0.35),
    key=lambda x: x["final_score"],
    reverse=True
)

print("\n>>> [CHRONORAG] Top Results (Time-Decayed Score):")
for rank, item in enumerate(chrono_results, 1):
    print(f"  Rank {rank}: [{item['id']} | Year: {item['year']}] Final Score: {item['final_score']:.4f} "
          f"(Base Sim: {item['cosine_sim']:.4f}, Decay: {item['decay_factor']:.4f})")
    print(f"         \"{item['text'][:85]}...\"")