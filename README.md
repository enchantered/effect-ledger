# Effect Ledger

**A durable, local guard between an AI agent's proposed tool call and a side effect.** Persist an action claim before running trusted tool code, reuse a completed receipt, and stop when the outcome is unknown.

The motivating problem appears in [recent framework issues and community discussions](docs/evidence.md): an action can succeed even when its confirmation is lost, so a workflow retry can repeat it. This project demonstrates a narrow, testable response. It is **not an AI model, agent framework, provider integration, or exactly-once delivery system**.

## Run it in a minute

Python 3.11+ and the standard library are enough. Download and unzip the repository, or obtain it with Git:

```sh
git clone https://github.com/enchantered/effect-ledger.git
cd effect-ledger
```

No package installation, API key, model download or runtime network access is required. Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
mkdir -p local-data
python3 -m effect_ledger demo --db local-data/normal.sqlite
python3 -m effect_ledger inspect --db local-data/normal.sqlite
```

On a fresh database, the demo prints:

```json
{"first_cached": false, "outbox_rows": 1, "second_cached": true}
```

The “effect” is a **synthetic local SQLite outbox insert**, not a real email or payment. The insert itself does not deduplicate calls: the guard is what prevents the second invocation. Run the same command again and both calls are cached; the row count remains one.

## See the uncertainty boundary

Use a different, fresh database:

```sh
python3 -m effect_ledger demo --db local-data/uncertain.sqlite --crash-after-effect
# Expected exit code 2: the fake effect happened, but no receipt was recorded.
python3 -m effect_ledger inspect --db local-data/uncertain.sqlite
python3 -m effect_ledger demo --db local-data/uncertain.sqlite
# Expected exit code 2 again: retry is blocked, not sent a second time.
```

The CLI flag injects an **exception after the local insert**; it does not terminate your Python process. The test suite separately uses abrupt subprocess termination to exercise a true process-death window. In either case, the same operation cannot automatically replay. The exception demo records `uncertain`; abrupt process death leaves `pending`.

`inspect` prints scope, operation ID, tool, state and timestamps—not arguments, argument hashes, receipts or raw callback errors. IDs and tool names are still visible: use synthetic or opaque values. Inspection creates an empty ledger if the path does not yet exist; it is not a read-only forensic tool.

For unresolved operations, use the separate **read-only uncertainty review** command:

```sh
python3 -m effect_ledger review --db local-data/uncertain.sqlite
python3 -m effect_ledger review --db local-data/uncertain.sqlite --limit 25 --scope demo
```

It emits JSON containing only `pending` and `uncertain` operation metadata, a `truncated` flag and `read_only: true`; the default page size is 100 (allowed range 1–1000). Each operation includes `age_hours` (whole elapsed hours since creation) and `older_than_72_hours`, calculated from the ledger's UTC creation timestamp. These fields help prioritize investigation; they are **not** a lease, proof that a callback stopped, or authorization to retry. Pending can mean a process died or may still be running; uncertain means the action may have completed. Both require checking an authoritative outcome before any manual decision: the suggested next step is `inspect_authoritative_outcome_no_auto_retry`. **Review does not resolve, replay, clear or mutate operations.** Unlike `inspect`, it fails if the database is missing and does not initialize a ledger. SQLite may use WAL coordination sidecars, so this is logical read-only access—not byte-for-byte forensic access or a security sandbox.

A successful review returns exit 0 even when operations need investigation: it reports state, not a successful external action. The row cap limits returned rows, not total database scan work; there is no next-page cursor. A truncated result is not the complete queue. Identifiers remain visible, so use opaque values. Read the [October 23 decision and technical mapping](docs/2026-10-23-decision.md), [living problem history](docs/consumer-behavior-log.md), and [portfolio arc](docs/portfolio-arc.md).

CLI exits: **0** completed command; **1** safe operational/validation error; **2** blocked or uncertain demo. Argument-parser errors also use **2**. Parent directories must already exist. Use a persistent file, not a memory database or a SQLite URI.

## Use the Python API

```python
from effect_ledger import Ledger, ConflictError, EffectFailed, OperationBlocked

ledger = Ledger("local-data/actions.sqlite")

def synthetic_tool():
    # Replace only after independently reviewing authorization and provider semantics.
    return {"receipt_id": "synthetic-receipt", "status": "done"}

try:
    result = ledger.execute(
        scope="sandbox-workflow",
        operation_id="logical-action-001",
        tool="synthetic.tool",
        arguments={"record": "sample-001"},
        callback=synthetic_tool,
    )
    print(result.cached, result.receipt)
except ConflictError:
    print("The operation identity is bound to different input.")
except (OperationBlocked, EffectFailed):
    print("Stop: investigate the authoritative outcome before doing anything else.")
```

The callback receives **no arguments**; the trusted caller supplies its closure. The caller must ensure the declared arguments describe the callback's actual behavior. The library cannot verify that correspondence. Scope and operation ID jointly identify a logical action. Preserve them across retries; use a new operation ID only for an intentionally separate authorized action. Never let a model assign a new retry identity merely to get past a block.

- Same scope + operation ID, same tool + canonical argument digest, completed: return the cached JSON receipt.
- Same identity, different tool or arguments: `ConflictError` before callback execution.
- Same identity, matching `pending` or `uncertain`: `OperationBlocked` before callback execution.
- Callback exception or invalid receipt: `EffectFailed`; the operation stays non-replayable.
- Two different operation IDs with identical arguments: two separate actions, intentionally.

Identifiers use `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`. Arguments and receipts must be finite JSON-compatible values with string object keys. Canonical object-key ordering makes reordered keys equivalent; this is not semantic normalization of numbers, whitespace inside strings, Unicode, timestamps or business entities. Arguments are limited to 1,000,000 encoded bytes and receipts to 64,000. These checks are not a hostile-input memory sandbox.

## What is persisted

A short SQLite transaction claims `(scope, operation_id)` and binds the tool and SHA-256 argument digest. The transaction ends **before** the callback starts. Success records a JSON receipt; a competing caller sees either a pending block or a completed cached receipt. No DB lock is deliberately held across the callback, and no timer expires an unresolved claim.

The ledger stores plaintext receipts, metadata and an unsalted argument hash. Original arguments are not retained, but low-entropy values can still be guessed from hashes. Database deletion, rollback, separate copies, fresh IDs and manual row edits can bypass the guard. A local receipt is not proof of remote delivery. See [safety boundaries](docs/safety.md).

## Tests and portfolio value

The offline tests cover durable caching, input conflicts, separate action identities, concurrent claims, invalid inputs, timeout/exception uncertainty, abrupt process death, receipt validation and payload-free CLI output. CI is configured for Python 3.11–3.13; a configured workflow is not evidence of a successful remote run.

This follows [Eval Gate](https://github.com/enchantered/eval-gate): output QA is useful, but consequential tool calls also need persistent execution state. It advances tool calling, state, guardrails, tests and observability without prematurely adding multi-agent orchestration. It is a separate prototype, not a live integration with earlier repositories. [Read the evidence and portfolio mapping](docs/evidence.md).

## Publication and reuse

Original implementation, synthetic examples, no third-party runtime dependencies or bundled assets. External discussions are paraphrased and linked, not copied as datasets or implementations. No open-source license is assigned in this initial release; public visibility does not imply unrestricted reuse rights. See the [public-release audit gate](docs/publication-audit.md). Keep real-user fixtures and databases out of Git.
