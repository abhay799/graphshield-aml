from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl

from sklearn.feature_extraction.text import TfidfVectorizer


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


def build_search_text(
    row: dict,
) -> str:

    parts = [
        row.get("title"),
        row.get("authority"),
        row.get("jurisdiction"),
        row.get("document_type"),
        row.get("version"),
        row.get("content"),
    ]

    return " ".join(
        str(value)
        for value in parts
        if value is not None
    )


def main() -> None:

    print("=" * 90)

    print(
        "GraphShield AML - "
        "Authoritative Policy Hybrid Index Builder"
    )

    print("=" * 90)

    if not CORPUS_PATH.exists():

        raise FileNotFoundError(
            f"Policy corpus missing: "
            f"{CORPUS_PATH}"
        )

    INDEX_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    corpus = pl.read_parquet(
        CORPUS_PATH
    )

    required_columns = {
        "chunk_id",
        "document_id",
        "title",
        "authority",
        "jurisdiction",
        "document_type",
        "version",
        "source_url",
        "page_number",
        "content",
        "document_sha256",
    }

    missing = (
        required_columns
        -
        set(corpus.columns)
    )

    if missing:

        raise RuntimeError(
            "Policy corpus is missing "
            f"required columns: "
            f"{sorted(missing)}"
        )

    if corpus.height == 0:

        raise RuntimeError(
            "Policy corpus contains zero chunks."
        )

    if (
        corpus["chunk_id"].n_unique()
        !=
        corpus.height
    ):

        raise RuntimeError(
            "Policy chunk IDs are not unique."
        )

    document_count = (
        corpus[
            "document_id"
        ]
        .n_unique()
    )

    if document_count != 6:

        raise RuntimeError(
            "Expected 6 authoritative "
            f"policy documents, found "
            f"{document_count}."
        )

    print(
        f"\nCorpus chunks : "
        f"{corpus.height:,}"
    )

    print(
        f"Documents     : "
        f"{document_count}"
    )

    rows = corpus.to_dicts()

    search_texts = [
        build_search_text(
            row
        )
        for row in rows
    ]

    # ==================================================
    # LEXICAL INDEX
    # ==================================================

    print(
        "\n[1/2] Building lexical "
        "TF-IDF index..."
    )

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        sublinear_tf=True,
        max_features=150_000,
        min_df=1,
    )

    tfidf_matrix = (
        vectorizer
        .fit_transform(
            search_texts
        )
    )

    lexical_artifact = {
        "vectorizer":
            vectorizer,

        "matrix":
            tfidf_matrix,

        "chunk_ids":
            corpus[
                "chunk_id"
            ]
            .to_list(),

        "document_ids":
            corpus[
                "document_id"
            ]
            .to_list(),
    }

    joblib.dump(
        lexical_artifact,
        TFIDF_PATH,
    )

    print(
        f"Vocabulary size : "
        f"{len(vectorizer.vocabulary_):,}"
    )

    print(
        f"TF-IDF shape    : "
        f"{tfidf_matrix.shape}"
    )

    # ==================================================
    # DENSE SEMANTIC INDEX
    # ==================================================

    print(
        "\n[2/2] Building dense "
        "semantic embeddings..."
    )

    try:

        from sentence_transformers import (
            SentenceTransformer,
        )

    except ImportError as exc:

        raise RuntimeError(
            "sentence-transformers is "
            "required for dense retrieval. "
            "Install with: "
            "python -m pip install "
            "sentence-transformers"
        ) from exc

    model = SentenceTransformer(
        DENSE_MODEL_NAME
    )

    dense_embeddings = model.encode(
        search_texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    dense_embeddings = (
        np.asarray(
            dense_embeddings,
            dtype=np.float32,
        )
    )

    if (
        dense_embeddings.shape[0]
        !=
        corpus.height
    ):

        raise RuntimeError(
            "Dense embedding row count "
            "does not match policy corpus."
        )

    if not np.isfinite(
        dense_embeddings
    ).all():

        raise RuntimeError(
            "Dense embeddings contain "
            "NaN or infinite values."
        )

    np.save(
        DENSE_PATH,
        dense_embeddings,
    )

    print(
        f"Dense shape     : "
        f"{dense_embeddings.shape}"
    )

    # ==================================================
    # ORDERED INDEX METADATA
    # ==================================================

    metadata = (
        corpus
        .with_row_index(
            "index_position"
        )
        .select(
            [
                "index_position",
                "chunk_id",
                "document_id",
                "title",
                "authority",
                "jurisdiction",
                "document_type",
                "version",
                "effective_date",
                "source_url",
                "local_file",
                "page_number",
                "chunk_index",
                "extraction_method",
                "document_sha256",
                "chunk_sha256",
            ]
        )
    )

    metadata.write_parquet(
        METADATA_PATH
    )

    corpus_hash = sha256_file(
        CORPUS_PATH
    )

    chunk_order_hash = hashlib.sha256(
        "\n".join(
            corpus[
                "chunk_id"
            ]
            .to_list()
        )
        .encode(
            "utf-8"
        )
    ).hexdigest()

    manifest = {
        "schema_version":
            "1.0",

        "created_at_utc":
            datetime.now(
                timezone.utc
            )
            .isoformat(),

        "corpus_path":
            str(
                CORPUS_PATH
                .relative_to(
                    PROJECT_ROOT
                )
            ),

        "corpus_sha256":
            corpus_hash,

        "document_count":
            document_count,

        "chunk_count":
            corpus.height,

        "chunk_order_sha256":
            chunk_order_hash,

        "lexical_index": {
            "type":
                "tfidf",

            "artifact":
                str(
                    TFIDF_PATH
                    .relative_to(
                        PROJECT_ROOT
                    )
                ),

            "vocabulary_size":
                len(
                    vectorizer.vocabulary_
                ),

            "shape":
                list(
                    tfidf_matrix.shape
                ),
        },

        "dense_index": {
            "type":
                "sentence_transformer",

            "model":
                DENSE_MODEL_NAME,

            "artifact":
                str(
                    DENSE_PATH
                    .relative_to(
                        PROJECT_ROOT
                    )
                ),

            "normalized":
                True,

            "shape":
                list(
                    dense_embeddings.shape
                ),
        },

        "metadata_artifact":
            str(
                METADATA_PATH
                .relative_to(
                    PROJECT_ROOT
                )
            ),
    }

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("-" * 90)

    print(
        f"Indexed chunks       : "
        f"{corpus.height:,}"
    )

    print(
        f"Indexed documents    : "
        f"{document_count}"
    )

    print(
        f"TF-IDF index         : "
        f"{TFIDF_PATH}"
    )

    print(
        f"Dense embeddings     : "
        f"{DENSE_PATH}"
    )

    print(
        f"Index metadata       : "
        f"{METADATA_PATH}"
    )

    print(
        f"Index manifest       : "
        f"{MANIFEST_PATH}"
    )

    print("-" * 90)

    print()
    print(
        "POLICY HYBRID INDEX BUILD COMPLETE"
    )


if __name__ == "__main__":
    main()
