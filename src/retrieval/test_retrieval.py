from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.append(
    str(
        PROJECT_ROOT
        / "src"
    )
)

from retrieval.retriever import (
    EvidenceRetriever,
)


CASE_ID = "PUT_CASE_ID_HERE"


def main():

    retriever = (
        EvidenceRetriever()
    )

    results = retriever.search(
        CASE_ID,
        (
            "Why was this transaction "
            "prioritized and what graph "
            "evidence exists?"
        ),
        top_k=5,
    )

    for item in results:

        print(
            "\n",
            item[
                "evidence_id"
            ],
        )

        print(
            "Source:",
            item[
                "source_type"
            ],
        )

        print(
            "Score:",
            round(
                item[
                    "retrieval_score"
                ],
                4,
            ),
        )

        print(
            item[
                "content"
            ],
        )


if __name__ == "__main__":
    main()