from pathlib import Path

import joblib
import polars as pl

from sklearn.feature_extraction.text import (
    TfidfVectorizer,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVIDENCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "evidence_documents.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "evidence_tfidf_index.joblib"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Evidence Retrieval Index")
    print("=" * 90)

    docs = pl.read_parquet(
        EVIDENCE_PATH
    )

    search_text = [
        (
            f"{row['source_type']} "
            f"{row['source_ref']} "
            f"{row['content']}"
        )
        for row in docs.iter_rows(
            named=True
        )
    ]

    vectorizer = TfidfVectorizer(
        lowercase=True,

        ngram_range=(
            1,
            2,
        ),

        sublinear_tf=True,

        max_features=100_000,
    )

    matrix = (
        vectorizer
        .fit_transform(
            search_text
        )
    )

    artifact = {
        "vectorizer":
            vectorizer,

        "matrix":
            matrix,

        "evidence_ids":
            docs[
                "evidence_id"
            ].to_list(),

        "case_ids":
            docs[
                "case_id"
            ].to_list(),
    }

    joblib.dump(
        artifact,
        OUTPUT_PATH,
    )

    print(
        f"\nDocuments indexed: "
        f"{docs.height:,}"
    )

    print(
        f"Vocabulary size: "
        f"{len(vectorizer.vocabulary_):,}"
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()