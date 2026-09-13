from sentence_transformers import SentenceTransformer


class EmbeddingModel:


    def __init__(self):

        self.model = SentenceTransformer(
            "BAAI/bge-small-zh-v1.5"
        )


    def encode(
        self,
        texts:list[str]
    ):

        return self.model.encode(
            texts,
            normalize_embeddings=True
        )