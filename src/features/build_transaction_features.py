import polars as pl
pl.concat_str(
    [
        pl.col("from_bank"),
        pl.col("from_account"),
    ],
    separator="::",
).alias("from_account_key"),

pl.concat_str(
    [
        pl.col("to_bank"),
        pl.col("to_account"),
    ],
    separator="::",
).alias("to_account_key"),

# lf = lf.select(
#     [
#         "transaction_id",
#         "source_row_number",
#         "event_ts",

#         "from_bank",
#         "from_account",
#         "from_account_key",

#         "to_bank",
#         "to_account",
#         "to_account_key",

#         "amount_paid",
#         "amount_received",

#         "payment_currency",
#         "receiving_currency",
#         "payment_format",

#         "hour_of_day",
#         "day_of_week",
#         "is_weekend",

#         "same_bank",
#         "cross_bank",

#         "same_currency",
#         "cross_currency",

#         "log_amount_paid",
#         "log_amount_received",

#         "amount_difference",

#         "is_laundering",
#     ]
# )