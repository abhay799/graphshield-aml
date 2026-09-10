from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import yaml
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "policy"
    / "source_registry.yaml"
)

RAW_DIR = (
    PROJECT_ROOT
    / "data"
    / "policy"
    / "raw"
)

PROCESSED_DIR = (
    PROJECT_ROOT
    / "data"
    / "policy"
    / "processed"
)

OUTPUT_PARQUET = (
    PROCESSED_DIR
    / "policy_corpus.parquet"
)

OUTPUT_JSONL = (
    PROCESSED_DIR
    / "policy_corpus.jsonl"
)

PROVENANCE_JSON = (
    PROCESSED_DIR
    / "policy_provenance.json"
)

CHUNK_SIZE = 1800
CHUNK_OVERLAP = 250

OCR_TARGET_FILE = "fiu_ind_aml_cft_guidelines_2026.pdf"

TESSERACT_CANDIDATES = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]

OCR_RENDER_SCALE = 3.0


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


def sha256_text(text: str) -> str:

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def clean_text(text: str) -> str:

    return " ".join(
        (text or "").split()
    )


def find_tesseract() -> Path:

    for candidate in TESSERACT_CANDIDATES:

        if candidate.exists():
            return candidate

    raise RuntimeError(
        "Tesseract OCR was not found. "
        "Expected installation under "
        "C:\\Program Files\\Tesseract-OCR."
    )


def ocr_pdf_pages(
    path: Path,
) -> list[tuple[int, str]]:

    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required for OCR fallback. "
            "Run: python -m pip install pymupdf"
        ) from exc

    tesseract = find_tesseract()

    print()
    print(
        "    Native PDF text extraction "
        "returned zero text."
    )
    print(
        "    Starting Tesseract OCR fallback..."
    )

    document = pymupdf.open(
        str(path)
    )

    results: list[
        tuple[int, str]
    ] = []

    try:

        with tempfile.TemporaryDirectory() as tmp:

            temp_dir = Path(tmp)

            total_pages = len(
                document
            )

            for page_index in range(
                total_pages
            ):

                page_number = (
                    page_index + 1
                )

                page = document[
                    page_index
                ]

                image_path = (
                    temp_dir
                    / f"page_{page_number:04d}.png"
                )

                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(
                        OCR_RENDER_SCALE,
                        OCR_RENDER_SCALE,
                    ),
                    alpha=False,
                )

                pixmap.save(
                    str(image_path)
                )

                result = subprocess.run(
                    [
                        str(tesseract),
                        str(image_path),
                        "stdout",
                        "-l",
                        "eng",
                        "--psm",
                        "3",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                )

                if result.returncode != 0:

                    raise RuntimeError(
                        "Tesseract failed on "
                        f"page {page_number}: "
                        f"{result.stderr.strip()}"
                    )

                page_text = clean_text(
                    result.stdout
                )

                if page_text:

                    results.append(
                        (
                            page_number,
                            page_text,
                        )
                    )

                print(
                    f"    OCR page "
                    f"{page_number}/{total_pages} "
                    f"chars={len(page_text)}"
                )

    finally:

        document.close()

    if not results:

        raise RuntimeError(
            "OCR completed but produced "
            "zero extractable text."
        )

    return results


def chunk_text(text: str) -> list[str]:

    text = clean_text(text)

    if not text:
        return []

    chunks = []

    start = 0

    while start < len(text):

        proposed_end = min(
            start + CHUNK_SIZE,
            len(text),
        )

        end = proposed_end

        if proposed_end < len(text):

            # Prefer ending on a sentence boundary.
            sentence_break = max(
                text.rfind(
                    ". ",
                    start,
                    proposed_end,
                ),
                text.rfind(
                    "? ",
                    start,
                    proposed_end,
                ),
                text.rfind(
                    "! ",
                    start,
                    proposed_end,
                ),
            )

            # Do not make the chunk too short just
            # because an early full stop exists.
            if (
                sentence_break
                >
                start + int(
                    CHUNK_SIZE * 0.60
                )
            ):
                end = (
                    sentence_break + 1
                )

        chunk = (
            text[
                start:end
            ]
            .strip()
        )

        if chunk:
            chunks.append(
                chunk
            )

        if end >= len(text):
            break

        start = max(
            end - CHUNK_OVERLAP,
            start + 1,
        )

    return chunks


def load_registry() -> dict:

    if not REGISTRY_PATH.exists():

        raise FileNotFoundError(
            f"Missing policy registry: "
            f"{REGISTRY_PATH}"
        )

    registry = yaml.safe_load(
        REGISTRY_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(
        registry,
        dict,
    ):

        raise ValueError(
            "source_registry.yaml "
            "must contain a YAML object."
        )

    sources = registry.get(
        "sources"
    )

    if not isinstance(
        sources,
        list,
    ) or not sources:

        raise ValueError(
            "source_registry.yaml "
            "must contain a non-empty "
            "'sources' list."
        )

    return registry


def main() -> None:

    print(
        "=" * 90
    )

    print(
        "GraphShield AML - "
        "Authoritative Policy Corpus Builder"
    )

    print(
        "=" * 90
    )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry = (
        load_registry()
    )

    sources = registry[
        "sources"
    ]

    print(
        f"\nRegistered policy documents: "
        f"{len(sources)}"
    )

    # --------------------------------------------------
    # Registry integrity checks
    # --------------------------------------------------

    document_ids = [
        source[
            "document_id"
        ]
        for source in sources
    ]

    local_files = [
        source[
            "local_file"
        ]
        for source in sources
    ]

    if (
        len(document_ids)
        !=
        len(set(document_ids))
    ):
        raise RuntimeError(
            "Duplicate document_id "
            "found in policy registry."
        )

    if (
        len(local_files)
        !=
        len(set(local_files))
    ):
        raise RuntimeError(
            "Duplicate local_file "
            "found in policy registry."
        )

    fatf = next(
        (
            source
            for source in sources
            if source[
                "document_id"
            ]
            ==
            "fatf_recommendations_2026"
        ),
        None,
    )

    if (
        fatf is None
        or fatf.get(
            "version"
        )
        !=
        "June 2026"
    ):
        raise RuntimeError(
            "FATF Recommendations "
            "must be registered as "
            "version 'June 2026'."
        )

    # --------------------------------------------------
    # Ensure registered raw files exist
    # --------------------------------------------------

    missing = []

    for source in sources:

        path = (
            RAW_DIR
            / source[
                "local_file"
            ]
        )

        if not path.exists():
            missing.append(
                str(path)
            )

    if missing:

        print(
            "\nMissing registered files:"
        )

        for path in missing:
            print(
                f" - {path}"
            )

        raise FileNotFoundError(
            "One or more registered "
            "policy files are missing."
        )

    actual_pdfs = {
        path.name
        for path
        in RAW_DIR.glob(
            "*.pdf"
        )
    }

    registered_pdfs = set(
        local_files
    )

    unregistered = (
        actual_pdfs
        -
        registered_pdfs
    )

    if unregistered:

        print(
            "\nWARNING: Unregistered PDFs "
            "were found and will NOT be "
            "silently added:"
        )

        for name in sorted(
            unregistered
        ):
            print(
                f" - {name}"
            )

    # --------------------------------------------------
    # Build corpus
    # --------------------------------------------------

    corpus_built_at_utc = (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )

    records = []
    provenance_documents = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        document_id = source[
            "document_id"
        ]

        local_file = source[
            "local_file"
        ]

        path = (
            RAW_DIR
            / local_file
        )

        print()
        print(
            f"[{index}/{len(sources)}] "
            f"{local_file}"
        )

        print(
            f"    document_id : "
            f"{document_id}"
        )

        print(
            f"    authority   : "
            f"{source.get('authority')}"
        )

        print(
            f"    version     : "
            f"{source.get('version')}"
        )

        document_sha256 = (
            sha256_file(
                path
            )
        )

        reader = PdfReader(
            str(path)
        )

        text_pages = 0
        document_chunks = 0
        ocr_fallback_used = False

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):

            page_text = (
                page.extract_text()
                or ""
            )

            page_text = (
                clean_text(
                    page_text
                )
            )

            if not page_text:
                continue

            text_pages += 1

            page_chunks = (
                chunk_text(
                    page_text
                )
            )

            for chunk_index, content in enumerate(
                page_chunks,
                start=1,
            ):

                chunk_id = (
                    f"{document_id}"
                    f"_p{page_number:04d}"
                    f"_c{chunk_index:03d}"
                )

                records.append(
                    {
                        "chunk_id":
                            chunk_id,

                        "document_id":
                            document_id,

                        "title":
                            source.get(
                                "title"
                            ),

                        "authority":
                            source.get(
                                "authority"
                            ),

                        "jurisdiction":
                            source.get(
                                "jurisdiction"
                            ),

                        "document_type":
                            source.get(
                                "document_type"
                            ),

                        "version":
                            source.get(
                                "version"
                            ),

                        "effective_date":
                            source.get(
                                "effective_date"
                            ),

                        "source_url":
                            source.get(
                                "source_url"
                            ),

                        "local_file":
                            local_file,

                        "source_type":
                            "pdf",

                        "extraction_method":
                            "pypdf",

                        "authoritative":
                            bool(
                                source.get(
                                    "authoritative",
                                    False,
                                )
                            ),

                        "page_number":
                            page_number,

                        "chunk_index":
                            chunk_index,

                        "document_sha256":
                            document_sha256,

                        "chunk_sha256":
                            sha256_text(
                                content
                            ),

                        "retrieved_at_utc":
                            source.get(
                                "retrieved_at_utc"
                            ),

                        "corpus_built_at_utc":
                            corpus_built_at_utc,

                        "content":
                            content,
                    }
                )

                document_chunks += 1

        # --------------------------------------------------
        # FIU-IND scanned PDF OCR fallback
        # --------------------------------------------------

        if (
            text_pages == 0
            and local_file == OCR_TARGET_FILE
        ):

            ocr_fallback_used = True

            ocr_pages = ocr_pdf_pages(
                path
            )

            for page_number, page_text in ocr_pages:

                text_pages += 1

                page_chunks = chunk_text(
                    page_text
                )

                for chunk_index, content in enumerate(
                    page_chunks,
                    start=1,
                ):

                    chunk_id = (
                        f"{document_id}"
                        f"_p{page_number:04d}"
                        f"_c{chunk_index:03d}"
                    )

                    records.append(
                        {
                            "chunk_id":
                                chunk_id,

                            "document_id":
                                document_id,

                            "title":
                                source.get(
                                    "title"
                                ),

                            "authority":
                                source.get(
                                    "authority"
                                ),

                            "jurisdiction":
                                source.get(
                                    "jurisdiction"
                                ),

                            "document_type":
                                source.get(
                                    "document_type"
                                ),

                            "version":
                                source.get(
                                    "version"
                                ),

                            "effective_date":
                                source.get(
                                    "effective_date"
                                ),

                            "source_url":
                                source.get(
                                    "source_url"
                                ),

                            "local_file":
                                local_file,

                            "source_type":
                                "pdf",

                            "extraction_method":
                                "tesseract_ocr",

                            "authoritative":
                                bool(
                                    source.get(
                                        "authoritative",
                                        False,
                                    )
                                ),

                            "page_number":
                                page_number,

                            "chunk_index":
                                chunk_index,

                            "document_sha256":
                                document_sha256,

                            "chunk_sha256":
                                sha256_text(
                                    content
                                ),

                            "retrieved_at_utc":
                                source.get(
                                    "retrieved_at_utc"
                                ),

                            "corpus_built_at_utc":
                                corpus_built_at_utc,

                            "content":
                                content,
                        }
                    )

                    document_chunks += 1

        file_stat = (
            path.stat()
        )

        local_file_mtime_utc = (
            datetime.fromtimestamp(
                file_stat.st_mtime,
                timezone.utc,
            )
            .isoformat()
        )

        provenance_documents.append(
            {
                "document_id":
                    document_id,

                "title":
                    source.get(
                        "title"
                    ),

                "authority":
                    source.get(
                        "authority"
                    ),

                "jurisdiction":
                    source.get(
                        "jurisdiction"
                    ),

                "document_type":
                    source.get(
                        "document_type"
                    ),

                "version":
                    source.get(
                        "version"
                    ),

                "effective_date":
                    source.get(
                        "effective_date"
                    ),

                "source_url":
                    source.get(
                        "source_url"
                    ),

                "local_file":
                    local_file,

                "authoritative":
                    bool(
                        source.get(
                            "authoritative",
                            False,
                        )
                    ),

                "document_sha256":
                    document_sha256,

                "file_size_bytes":
                    file_stat.st_size,

                "pdf_pages":
                    len(
                        reader.pages
                    ),

                "pages_with_text":
                    text_pages,

                "ocr_fallback_used":
                    ocr_fallback_used,

                "chunks":
                    document_chunks,

                "retrieved_at_utc":
                    source.get(
                        "retrieved_at_utc"
                    ),

                "local_file_mtime_utc":
                    local_file_mtime_utc,
            }
        )

        print(
            f"    SHA-256     : "
            f"{document_sha256}"
        )

        print(
            f"    PDF pages   : "
            f"{len(reader.pages)}"
        )

        print(
            f"    text pages  : "
            f"{text_pages}"
        )

        print(
            f"    chunks      : "
            f"{document_chunks}"
        )

    if not records:

        raise RuntimeError(
            "No policy corpus chunks "
            "were generated."
        )

    # --------------------------------------------------
    # Final corpus integrity
    # --------------------------------------------------

    corpus = pl.DataFrame(
        records,
        infer_schema_length=None,
    )

    unique_chunks = (
        corpus[
            "chunk_id"
        ]
        .n_unique()
    )

    if (
        unique_chunks
        !=
        corpus.height
    ):

        raise RuntimeError(
            "Duplicate policy chunk_id "
            "detected."
        )

    processed_documents = (
        corpus[
            "document_id"
        ]
        .n_unique()
    )

    if (
        processed_documents
        !=
        len(sources)
    ):

        raise RuntimeError(
            "Not every registered policy "
            "document produced corpus text."
        )

    corpus.write_parquet(
        OUTPUT_PARQUET
    )

    with OUTPUT_JSONL.open(
        "w",
        encoding="utf-8",
    ) as handle:

        for record in records:

            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                +
                "\n"
            )

    provenance = {
        "schema_version":
            registry.get(
                "schema_version",
                "1.0",
            ),

        "corpus_built_at_utc":
            corpus_built_at_utc,

        "registered_document_count":
            len(
                sources
            ),

        "processed_document_count":
            processed_documents,

        "chunk_count":
            corpus.height,

        "all_sources_authoritative":
            all(
                bool(
                    source.get(
                        "authoritative",
                        False,
                    )
                )
                for source
                in sources
            ),

        "documents":
            provenance_documents,
    }

    PROVENANCE_JSON.write_text(
        json.dumps(
            provenance,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "-" * 90
    )

    print(
        f"Documents processed : "
        f"{processed_documents}"
    )

    print(
        f"Corpus chunks       : "
        f"{corpus.height}"
    )

    print(
        f"Unique chunk IDs    : "
        f"{unique_chunks}"
    )

    print(
        f"Parquet             : "
        f"{OUTPUT_PARQUET}"
    )

    print(
        f"JSONL               : "
        f"{OUTPUT_JSONL}"
    )

    print(
        f"Provenance          : "
        f"{PROVENANCE_JSON}"
    )

    print(
        "-" * 90
    )

    print()
    print(
        "POLICY CORPUS BUILD COMPLETE"
    )


if __name__ == "__main__":
    main()
