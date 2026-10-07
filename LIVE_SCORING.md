# Live Scoring

## Scope and safety boundary

GraphShield AML is a research / portfolio decision-support platform. The live
transaction scorer is a **synthetic/research demo scoring surface**, not a real
fraud-detection service and not a production banking decision engine.

Use public or synthetic data only for portfolio/academic demonstrations. The
scorer does not autonomously block accounts, close cases, file SAR/STR reports,
submit regulatory reports, or replace legal/compliance judgment. Human review
remains required for investigation outcomes.

The live-scoring endpoint currently exists in the local development environment.
It is **not yet deployed as part of the public Railway demo** and this document
does not claim that POST /score/transaction is reachable at the public demo URL.

## Endpoint: POST /score/transaction

POST /score/transaction accepts one raw transaction with:

- transaction_id
- event_ts
- from_bank
- from_account
- to_bank
- to_account
- amount_paid
- amount_received
- payment_currency
- receiving_currency
- payment_format

The local scoring path is:

1. validate and normalize the raw transaction with the existing online feature contract
2. read pre-existing Redis history for sender, receiver, pair, bank-pair, counterparty, graph-neighbor, velocity, and pass-through state
3. compute the frozen 70-feature vector through FrozenModelFeatureWrapper
4. apply the frozen Graph LightGBM model (models/lightgbm_graph_v1.joblib)
5. apply the frozen Platt calibrator (models/probability_calibrator_graph_v1.joblib)
6. return the raw model probability, calibrated score, separate sender/receiver history status, and explicit research/safety flags
7. after a successful score, pass the transaction through GuardedLiveStateWriter; only a forward-valid, non-duplicate event is delegated to the unchanged certified commit_group(), so later live requests can observe warm-state history in Redis

The scoring service validates the live feature contract, the LightGBM feature
schema, the calibrator feature schema, and the calibration method before it can
produce a score.

## Mode A: forward-only live-state contract

POST /score/transaction is a **forward-only live runtime** surface. Its
correctness claim is limited to the current Redis runtime frontier: accepted
transactions may advance state forward in time, but this endpoint does not
provide point-in-time historical re-scoring fidelity.

GuardedLiveStateWriter stores two runtime-only guard records in the same Redis
namespace: a monotonic event-time watermark and a committed transaction-ID
registry. A request whose event timestamp is older than the current watermark
is rejected with HTTP 409 and is not committed. Reuse of a transaction_id that
has already been committed in the namespace is also rejected with HTTP 409.
Same-timestamp events are supported by the guard as one commit_group; the
watermark advances only after the group commit succeeds.

The guard deliberately wraps the certified Engine rather than modifying
src/streaming/phase10_b3_online_feature_parity.py or
src/services/live_scoring_feature_wrapper.py.

A nonempty namespace created before Mode A guard metadata existed is rejected
fail-closed instead of being silently adopted. In particular, the earlier
case-queue bootstrap namespace is not automatically a valid Mode A live
namespace. Deployment must use a fresh forward-only namespace or a separately
certified migration/bootstrap procedure that establishes a correct live
frontier.

Historical transactions and certification replays belong to a separate PIT
replay mode; they must not be injected into the persistent live namespace.

## Mode B: historical PIT replay for certification only

Historical point-in-time fidelity is intentionally separated from the Mode A
live API. The certification script is:

`scripts/live_scoring/historical_pit_replay.py`

Mode B has **no public endpoint**, is not invoked by
`POST /score/transaction`, and must never write into the persistent Mode A
live namespace. It exists solely to produce historical fidelity/certification
evidence.

The script starts from one clean dedicated Redis namespace. Requested targets
are sorted by `event_ts`; their original L2 case-specific prior-history scopes
are unioned and de-duplicated, then replayed once in strict chronological
timestamp-group order. For any timestamp containing a target, the complete
timestamp group is featured first and every requested target result is recorded
before that group is committed through the unchanged certified
`Engine.commit_group()`.

Therefore each target sees only state from timestamps strictly earlier than its
own timestamp, while multiple targets can share one forward-moving historical
replay without injecting older rows after the replay frontier has advanced.

The frozen 70-feature contract, LightGBM model, and Platt calibrator are loaded
directly. Mode B does not call the live HTTP API or
`GuardedLiveStateWriter`. Evidence JSON records the target transaction,
replayed row and timestamp-group counts, the complete 70-feature vector in
frozen model order, the raw model score, calibrated score, and comparison with
the certified gold feature row/reference where available.

The default verification target is `IBM_LI_SMALL_4884658`. Its certified
reference values are:

- raw model score: `0.9999999999996636`
- calibrated score: `0.02738545245606547`

The L4c Mode B verification replay reproduced those values exactly after
replaying 3,727 strictly prior rows across 2,852 timestamp groups. The replayed
70-feature vector had 0 mismatches against the certified gold row:

- raw model score: `0.9999999999996636`
- calibrated score: `0.02738545245606547`
- certified feature mismatches: `0 / 70`
- evidence: `reports/v2/phase10/l4c_historical_pit_replay_ibm.json`

The temporary certification namespace was cleaned after evidence capture. Mode B
remains certification-only and is not a user-facing historical scoring service
or public/production feature.

## Cold start versus warm state

A transaction can be scored when either account has no pre-existing Redis
history. In that case the engine uses the documented cold-start semantics:
history counts and sums are zero, undefined historical averages/time-since
values remain missing, and new-pair flags are set accordingly.

The API reports sender and receiver history independently:

- known: Redis contained prior transaction history for that account before the current transaction was scored
- unknown: Redis did not contain prior transaction history for that account

If either side is unknown, the response sets limited_signal: true and returns a
limitation note explaining that network/history-based signals are unavailable or
incomplete for first-time accounts.

A pre-Mode-A local L3 fidelity verification replayed the established-pair case
CASE_IBM_LI_SMALL_4884658 using the same point-in-time warm-state replay approach
used in L2: 3,727 historical rows across 2,852 timestamp groups. That result is
historical certification evidence; it is **not** a claim that the Mode A live
endpoint can accept an arbitrary old transaction after its runtime frontier has
advanced.

The populated warm-state transaction produced:

- raw model score: `0.9999999999996636`
- calibrated score: `0.02738545245606547`

The same transaction shape with fresh synthetic sender/receiver account IDs in
an empty Redis namespace produced:

- raw model score: `0.000370085682650635`
- calibrated score: `0.0006321802023871719`

The calibrated warm-state score was therefore **43.3190605347x** the cold/unknown
score in that verification. This demonstrates that historical/network state
changes the model input and resulting score. It is **not** a claim of real-world
fraud probability, detection accuracy, or production-bank performance.

## Redis runtime state

The scorer may update Redis only through GuardedLiveStateWriter after a successful
score. The guard enforces forward-only event time and transaction-ID idempotency
before delegating the state mutation to the unchanged certified commit_group().
That mutation lets forward-moving research/demo transactions build sender,
receiver, pair, graph, velocity, and pass-through history.

Redis state is **mutable runtime state**, in the same category as the existing
SQLite/DuckDB runtime stores described in
docs/reproducibility/ARTIFACT_HANDOFF.md. It is not a canonical model/data
artifact.

The live scorer does not write to:

- data/processed/cases/case_queue.parquet
- frozen model or calibration artifacts
- certification reports
- Git-tracked canonical artifacts

API responses make this boundary explicit with:

- scoring_mode: live_research_only
- boundary: synthetic_research_demo_only
- synthetic_research_demo_only: true
- canonical_artifacts_modified: false

/health continues to report mode: read_only for canonical analyst/case
operations and separately reports live scoring as scoring_mode:
live_research_only with Redis-only runtime state.

## Frozen-model pass-through compatibility limitation

The live scorer wraps the certified Phase 10 B3 Engine; it does not modify
src/streaming/phase10_b3_online_feature_parity.py.

**Known frozen-model compatibility limitation:** sender_recent_inbound_count_24h
and the related sender_recent_inbound_amount_24h and
sender_last_inbound_ts_24h fields intentionally replicate an offline
training-pipeline quirk.

The offline V5 feature pipeline builds the rolling inbound aggregate on inbound
event timestamps and then attaches it to the current sender through an
**exact event_ts join**. That is not the same as performing a true arbitrary
24-hour lookup for every scored event.

The live wrapper intentionally reproduces that exact-timestamp join behavior for
fidelity with the frozen model. This is a known limitation of the current model
generation, not a bug in the live scorer. Correcting the offline semantics would
require regenerating features, retraining, and recertifying the model and is out
of scope for this feature.

The offline rolling window itself uses closed="left", so when an exact timestamp
anchor exists the aggregate covers the preceding 24 hours and excludes the
current timestamp group. If no inbound anchor exists for the sender/currency at
the exact current event_ts, the frozen offline semantics are count 0, amount
0.0, and last inbound timestamp None.

Only sender_recent_inbound_count_24h belongs to the frozen 70-feature model
contract. The amount and timestamp fields are retained as compatibility metadata
so their shared training-pipeline behavior remains explicit without changing the
model feature-vector width.


## CSV Batch Demo

The static portfolio supports frontend-only CSV orchestration through the
unchanged POST /score/transaction endpoint. No backend batch endpoint or new
model/calibration behavior is introduced.

Use only synthetic or anonymized transaction data, consistent with the public
or synthetic research / portfolio boundary. Do not include real bank account
numbers, card numbers, UPI IDs, names, addresses, phone numbers, emails,
government identifiers, or personally identifying financial data.

The original UTF-8 CSV remains browser-local: it is parsed in page memory, never
uploaded as a file or automatically persisted. Only validated selected rows are
sent as 11-field JSON requests. Successful requests update Redis runtime history;
this is not a claim of zero server-side retention. Clear/reset or reload discards
page data, not Redis history or already submitted transactions.

Limits: 100 nonblank transaction records (including invalid rows), 256 KiB,
32 columns, and 1024 characters per cell. Oversized input is rejected rather
than truncated. Required headers are case-sensitive and may be reordered;
extra non-label columns are ignored and excluded from requests. Runtime labels
such as is_laundering are rejected. All duplicate transaction IDs are invalid in the CSV UI, and the Mode A backend
independently rejects any transaction_id already committed in its live namespace. Identifiers
remain strings. Amounts must be finite nonnegative decimals. Timestamps use
YYYY-MM-DDTHH:mm:ss with optional 1?6 fractional digits and Z or ?HH:mm; absent
offsets mean UTC. Timestamp text and offsets are preserved.

Valid rows must have nondecreasing UTC timestamps; decreasing order blocks
scoring without automatic sorting. Equal timestamps retain CSV order. Execution
is deterministic and sequential, with one request at a time, a frozen API URL
and queue, and a shared manual/batch guard. There is no automatic retry.
Attempted rows cannot be resubmitted within the current dataset; previously
batch-submitted IDs remain blocked after clear/reload of a CSV in the same page.

Stopping after the current request prevents future submissions only: it does
not abort the current request or roll back transactions. Completed rows stay
visible and remaining rows are Not submitted. After a clean stop, remaining
never-submitted valid rows can be explicitly scored later; nothing resumes
automatically. A definitive API error or malformed response stops the queue and
preserves partial completion. Timeout/transport loss is Completion unknown:
backend processing and Redis mutation may still occur, so further scoring in
that page is disabled. Check backend completion before reloading; reload is not
a rollback or safe-retry guarantee.

This is an ordered sequence of live scoring requests, not an atomic historical
replay. Equal-timestamp requests do not supply a complete timestamp group for
offline replay parity. Existing Redis history, manual requests, and other
clients/tabs can affect results; the page guard does not coordinate other
clients or create a fresh namespace.

Results preserve backend raw/calibrated values, account-history status,
limited_signal, runtime and research boundary metadata. Missing optional
metadata is Unavailable, not a fabricated default. Selected-row details show
the backend feature breakdown for read-only input inspection, not causality.
No fraud verdict or enforcement recommendation is generated.

The CSV UI has no public deployment or production-readiness certification.
Stateful real API batch verification belongs to L6A Step 3; Step 2 uses
controlled transport tests only.
