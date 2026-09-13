from app.rag.loader import load_complaints
from app.rag.case_builder import build_case_document
from app.rag.embedding import EmbeddingModel
from app.storage.vector_store import VectorStore



rows=load_complaints(
    "data/complaints.csv"
)



documents=[
    build_case_document(row)
    for row in rows[:1000]
]



embedder=EmbeddingModel()



vectors=embedder.encode(

    [
        doc.content
        for doc in documents
    ]

)



store=VectorStore()



store.add_documents(
    documents,
    vectors
)



print(
    "insert success",
    len(documents)
)