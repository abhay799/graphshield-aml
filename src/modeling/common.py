from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)

MODEL_DIR = PROJECT_ROOT / "models"

REPORT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
)

PREDICTION_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "modeling"
)


TARGET = "is_laundering"
SPLIT_COL = "split"


CATEGORICAL_COLUMNS = [
    "payment_format",
    "payment_currency",
    "receiving_currency",
]


EXCLUDED_COLUMNS = {
    "transaction_id",
    "event_ts",

    "from_account_key",
    "to_account_key",

    # Leakage-validation only
    "sender_prev_event_ts",
    "receiver_prev_event_ts",
    "sender_last_inbound_ts_1h",

    TARGET,
    SPLIT_COL,
}


def ensure_directories():

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    PREDICTION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def get_feature_columns():

    schema = (
        pl.scan_parquet(DATA_PATH)
        .collect_schema()
    )

    all_columns = schema.names()

    features = [
        column
        for column in all_columns
        if column not in EXCLUDED_COLUMNS
    ]

    categorical = [
        column
        for column in CATEGORICAL_COLUMNS
        if column in features
    ]

    numerical = [
        column
        for column in features
        if column not in categorical
    ]

    return features, numerical, categorical


def scan_split(
    split_name,
    feature_columns,
    train_fraction=1.0,
):

    columns = list(
        dict.fromkeys(
            [
                "transaction_id",
                *feature_columns,
                TARGET,
            ]
        )
    )

    lf = (
        pl.scan_parquet(DATA_PATH)
        .filter(
            pl.col(SPLIT_COL)
            == split_name
        )
        .select(columns)
    )

    # Optional deterministic sampling of TRAIN only.
    # Validation/test are always kept intact.
    if (
        split_name == "train"
        and train_fraction < 1.0
    ):

        threshold = int(
            train_fraction * 1_000_000
        )

        lf = lf.filter(
            (
                pl.col("transaction_id")
                .hash(seed=42)
                % 1_000_000
            )
            < threshold
        )

    return lf


def load_numeric_split(
    split_name,
    numerical_features,
    train_fraction=1.0,
):

    lf = scan_split(
        split_name,
        numerical_features,
        train_fraction,
    )

    lf = lf.with_columns(
        [
            pl.col(column)
            .cast(pl.Float32)
            for column in numerical_features
        ]
    )

    df = lf.collect()

    transaction_ids = (
        df["transaction_id"]
        .to_numpy()
    )

    X = (
        df.select(numerical_features)
        .to_numpy()
    )

    y = (
        df[TARGET]
        .to_numpy()
        .astype("int8")
    )

    return transaction_ids, X, y


def load_tree_split(
    split_name,
    features,
    numerical_features,
    categorical_features,
    train_fraction=1.0,
):

    lf = scan_split(
        split_name,
        features,
        train_fraction,
    )

    expressions = []

    for column in numerical_features:

        expressions.append(
            pl.col(column)
            .cast(pl.Float32)
        )

    for column in categorical_features:

        expressions.append(
            pl.col(column)
            .cast(pl.String)
            .fill_null("__MISSING__")
        )

    lf = lf.with_columns(expressions)

    df = lf.collect()

    pdf = df.to_pandas()

    transaction_ids = pdf.pop(
        "transaction_id"
    )

    y = (
        pdf.pop(TARGET)
        .astype("int8")
        .to_numpy()
    )

    for column in categorical_features:

        pdf[column] = (
            pdf[column]
            .astype("category")
        )

    return transaction_ids, pdf, y