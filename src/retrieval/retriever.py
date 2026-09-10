from pathlib import Path

import joblib
import numpy as np
import polars as pl

from sklearn.metrics.pairwise import (
    cosine_similarity,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVIDENCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "evidence_documents.parquet"
)

INDEX_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "evidence_tfidf_index.joblib"
)


class EvidenceRetriever:

    def __init__(self):

        self.docs = (
            pl.read_parquet(
                EVIDENCE_PATH
            )
        )

        artifact = joblib.load(
            INDEX_PATH
        )

        self.vectorizer = artifact[
            "vectorizer"
        ]

        self.matrix = artifact[
            "matrix"
        ]

        self.case_ids = np.array(
            artifact[
                "case_ids"
            ],
            dtype=object,
        )

    def search(
        self,
        case_id,
        query,
        top_k=6,
    ):

        case_indices = np.flatnonzero(
            self.case_ids
            == case_id
        )

        if len(case_indices) == 0:
            return []

        query_vector = (
            self.vectorizer
            .transform(
                [query]
            )
        )

        similarities = (
            cosine_similarity(
                query_vector,
                self.matrix[
                    case_indices
                ],
            )
            .ravel()
        )

        ranking = np.argsort(
            similarities
        )[::-1]

        results = []

        for local_index in (
            ranking[
                :top_k
            ]
        ):

            global_index = int(
                case_indices[
                    local_index
                ]
            )

            row = self.docs.row(
                global_index,
                named=True,
            )

            results.append(
                {
                    **row,

                    "retrieval_score":
                        float(
                            similarities[
                                local_index
                            ]
                        ),
                }
            )

        return results

    def source_type(
        self,
        case_id,
        source_type,
    ):

        return (
            self.docs
            .filter(
                (
                    pl.col("case_id")
                    == case_id
                )
                &
                (
                    pl.col("source_type")
                    == source_type
                )
            )
            .to_dicts()
        )