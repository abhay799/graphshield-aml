from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import polars as pl

from sentence_transformers import (
    CrossEncoder,
    SentenceTransformer,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CORPUS_PATH = (
    PROJECT_ROOT
    / "data"
    / "policy"
    / "processed"
    / "policy_corpus.parquet"
)

INDEX_DIR = (
    PROJECT_ROOT
    / "data"
    / "policy"
    / "indexes"
)

TFIDF_PATH = (
    INDEX_DIR
    / "policy_tfidf_index.joblib"
)

DENSE_PATH = (
    INDEX_DIR
    / "policy_dense_embeddings.npy"
)

METADATA_PATH = (
    INDEX_DIR
    / "policy_index_metadata.parquet"
)

MANIFEST_PATH = (
    INDEX_DIR
    / "policy_index_manifest.json"
)

DENSE_MODEL_NAME = (
    "sentence-transformers/all-MiniLM-L6-v2"
)

RERANK_MODEL_NAME = (
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

RRF_K = 60

LEXICAL_CANDIDATES = 40
DENSE_CANDIDATES = 40
RERANK_CANDIDATES = 20


def sha256_file(path: Path) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        for block in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


class PolicyRetriever:

    def __init__(
        self,
        enable_reranker: bool = True,
    ):

        self._validate_artifacts()

        self.corpus = pl.read_parquet(
            CORPUS_PATH
        )

        self.metadata = pl.read_parquet(
            METADATA_PATH
        )

        lexical = joblib.load(
            TFIDF_PATH
        )

        self.vectorizer = lexical[
            "vectorizer"
        ]

        self.tfidf_matrix = lexical[
            "matrix"
        ]

        self.chunk_ids = np.asarray(
            lexical[
                "chunk_ids"
            ],
            dtype=object,
        )

        self.dense_embeddings = np.load(
            DENSE_PATH
        )

        self.dense_model = SentenceTransformer(
            DENSE_MODEL_NAME
        )

        self.enable_reranker = (
            enable_reranker
        )

        self.reranker = None

        if self.enable_reranker:

            self.reranker = CrossEncoder(
                RERANK_MODEL_NAME
            )

        self._validate_alignment()

    def _validate_artifacts(
        self,
    ) -> None:

        required = [
            CORPUS_PATH,
            TFIDF_PATH,
            DENSE_PATH,
            METADATA_PATH,
            MANIFEST_PATH,
        ]

        missing = [
            str(path)
            for path in required
            if not path.exists()
        ]

        if missing:

            raise FileNotFoundError(
                "Missing policy retrieval "
                f"artifacts: {missing}"
            )

        manifest = json.loads(
            MANIFEST_PATH.read_text(
                encoding="utf-8"
            )
        )

        current_hash = sha256_file(
            CORPUS_PATH
        )

        expected_hash = manifest.get(
            "corpus_sha256"
        )

        if (
            expected_hash
            and current_hash
            != expected_hash
        ):

            raise RuntimeError(
                "Policy corpus changed after "
                "the retrieval index was built. "
                "Rebuild the policy index."
            )

    def _validate_alignment(
        self,
    ) -> None:

        n = self.corpus.height

        if len(
            self.chunk_ids
        ) != n:

            raise RuntimeError(
                "TF-IDF chunk alignment "
                "does not match corpus."
            )

        if (
            self.dense_embeddings.shape[0]
            != n
        ):

            raise RuntimeError(
                "Dense embedding alignment "
                "does not match corpus."
            )

        corpus_ids = np.asarray(
            self.corpus[
                "chunk_id"
            ].to_list(),
            dtype=object,
        )

        if not np.array_equal(
            corpus_ids,
            self.chunk_ids,
        ):

            raise RuntimeError(
                "Policy chunk ordering mismatch."
            )

    @staticmethod
    def _top_indices(
        scores: np.ndarray,
        top_n: int,
    ) -> np.ndarray:

        top_n = min(
            top_n,
            len(scores),
        )

        return np.argsort(
            scores
        )[::-1][:top_n]

    @staticmethod
    def _rrf(
        lexical_rank: list[int],
        dense_rank: list[int],
    ) -> dict[int, float]:

        scores: dict[
            int,
            float,
        ] = {}

        for rank, idx in enumerate(
            lexical_rank,
            start=1,
        ):

            scores[idx] = (
                scores.get(
                    idx,
                    0.0,
                )
                +
                1.0
                /
                (
                    RRF_K
                    +
                    rank
                )
            )

        for rank, idx in enumerate(
            dense_rank,
            start=1,
        ):

            scores[idx] = (
                scores.get(
                    idx,
                    0.0,
                )
                +
                1.0
                /
                (
                    RRF_K
                    +
                    rank
                )
            )

        return scores

    def search(
        self,
        query: str,
        top_k: int = 6,
        jurisdiction: str | None = None,
    ) -> list[dict]:

        query = (
            query or ""
        ).strip()

        if not query:

            return []

        # ------------------------------------------
        # Lexical retrieval
        # ------------------------------------------

        lexical_query = (
            self.vectorizer
            .transform(
                [query]
            )
        )

        lexical_scores = (
            self.tfidf_matrix
            @ lexical_query.T
        ).toarray().ravel()

        # ------------------------------------------
        # Dense semantic retrieval
        # ------------------------------------------

        dense_query = (
            self.dense_model.encode(
                [query],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )[0]
        )

        dense_scores = (
            self.dense_embeddings
            @ dense_query
        )

        # ------------------------------------------
        # Optional jurisdiction filtering
        # ------------------------------------------

        allowed = None

        if jurisdiction:

            allowed = set(
                self.corpus
                .with_row_index(
                    "_row"
                )
                .filter(
                    pl.col(
                        "jurisdiction"
                    )
                    .str.to_lowercase()
                    ==
                    jurisdiction.lower()
                )[
                    "_row"
                ]
                .to_list()
            )

        lexical_rank = [
            int(index)
            for index in self._top_indices(
                lexical_scores,
                LEXICAL_CANDIDATES,
            )
            if (
                allowed is None
                or int(index) in allowed
            )
        ]

        dense_rank = [
            int(index)
            for index in self._top_indices(
                dense_scores,
                DENSE_CANDIDATES,
            )
            if (
                allowed is None
                or int(index) in allowed
            )
        ]

        fused_scores = self._rrf(
            lexical_rank,
            dense_rank,
        )

        fused_rank = sorted(
            fused_scores,
            key=fused_scores.get,
            reverse=True,
        )

        candidate_indices = (
            fused_rank[
                :RERANK_CANDIDATES
            ]
        )

        if not candidate_indices:

            return []

        # ------------------------------------------
        # Cross-encoder reranking
        # ------------------------------------------

        rerank_scores = None

        if (
            self.enable_reranker
            and self.reranker
            is not None
        ):

            pairs = [
                (
                    query,
                    self.corpus.row(
                        index,
                        named=True,
                    )[
                        "content"
                    ],
                )
                for index
                in candidate_indices
            ]

            rerank_scores = np.asarray(
                self.reranker.predict(
                    pairs,
                    show_progress_bar=False,
                ),
                dtype=float,
            )

            rerank_order = np.argsort(
                rerank_scores
            )[::-1]

            candidate_indices = [
                candidate_indices[
                    int(local_index)
                ]
                for local_index
                in rerank_order
            ]

        # ------------------------------------------
        # Build citation-ready results
        # ------------------------------------------

        results = []

        for rank, index in enumerate(
            candidate_indices[
                :top_k
            ],
            start=1,
        ):

            row = self.corpus.row(
                index,
                named=True,
            )

            lexical_score = float(
                lexical_scores[
                    index
                ]
            )

            dense_score = float(
                dense_scores[
                    index
                ]
            )

            fusion_score = float(
                fused_scores.get(
                    index,
                    0.0,
                )
            )

            rerank_score = None

            if rerank_scores is not None:

                original_position = (
                    candidate_indices.index(
                        index
                    )
                )

                # Ranking is authoritative here;
                # numeric rerank score is optional.
                rerank_score = float(
                    self.reranker.predict(
                        [
                            (
                                query,
                                row[
                                    "content"
                                ],
                            )
                        ],
                        show_progress_bar=False,
                    )[0]
                )

            citation = (
                f"{row['authority']} | "
                f"{row['title']} | "
                f"{row['version']} | "
                f"page {row['page_number']} | "
                f"{row['chunk_id']}"
            )

            results.append(
                {
                    **row,

                    "rank":
                        rank,

                    "lexical_score":
                        lexical_score,

                    "dense_score":
                        dense_score,

                    "fusion_score":
                        fusion_score,

                    "rerank_score":
                        rerank_score,

                    "citation":
                        citation,
                }
            )

        return results


def main() -> None:

    print(
        "=" * 90
    )

    print(
        "GraphShield AML - "
        "Policy Hybrid Retriever Smoke Test"
    )

    print(
        "=" * 90
    )

    retriever = PolicyRetriever(
        enable_reranker=True
    )

    query = (
        "What does a risk-based approach "
        "require for customer due diligence "
        "and ongoing monitoring?"
    )

    print(
        f"\nQuery:\n{query}\n"
    )

    results = retriever.search(
        query,
        top_k=5,
    )

    for result in results:

        print(
            "-" * 90
        )

        print(
            f"Rank: "
            f"{result['rank']}"
        )

        print(
            f"Citation: "
            f"{result['citation']}"
        )

        print(
            f"Lexical: "
            f"{result['lexical_score']:.4f}"
        )

        print(
            f"Dense: "
            f"{result['dense_score']:.4f}"
        )

        print(
            f"Fusion: "
            f"{result['fusion_score']:.6f}"
        )

        if (
            result[
                "rerank_score"
            ]
            is not None
        ):

            print(
                f"Rerank: "
                f"{result['rerank_score']:.4f}"
            )

        print()

        print(
            result[
                "content"
            ][
                :700
            ]
        )

        print()

    if not results:

        raise RuntimeError(
            "Policy retrieval returned "
            "zero results."
        )

    print(
        "POLICY HYBRID RETRIEVER "
        "SMOKE TEST COMPLETE"
    )


if __name__ == "__main__":
    main()
