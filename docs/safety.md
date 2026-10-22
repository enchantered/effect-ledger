# Safety and failure boundaries

## A claim is not a receipt

The SQLite claim and a remote provider's action are separate commits. A process may die between them. A pending operation therefore means **unknown**, not “safe to retry.” A callback exception also does not prove that the external action failed. Effect Ledger blocks both cases under the same scope and operation ID. There is no lease expiry, reset button, automatic retry, or reconciliation command.

An operator must investigate against an authoritative provider before designing a recovery path. Manually deleting the row, changing scope or generating a new operation ID bypasses the guard and can repeat the action. A completed local receipt is not cryptographic proof that an external provider performed an action.

## Trusted caller responsibilities

A trusted application assigns the scope and logical operation ID before execution and preserves them across retries. Do not let a model invent a fresh ID for every attempt. Two intentionally separate requests should get different operation IDs even when their arguments match. Scope must include any tenant/account/side-effect boundary required by the application; the library does not authenticate it.

The callback is trusted Python code supplied by the developer. JSON inputs do not select commands or import functions. The demo has no network transport and performs no real email, payment, filesystem cleanup, or customer action. A future integration would need authorization, provider idempotency, receipt verification and domain-specific reconciliation in addition to this library.

## Local data is not a secret vault

The ledger stores opaque identifiers, a tool name, argument digest, state and JSON receipt. It does not retain original arguments. Low-entropy arguments can still be guessed from their digest, and a receipt can contain whatever a callback returns, including private data. Database content is plaintext; identifiers and tool names can also identify people if callers choose them poorly. Use synthetic examples and protect local storage with normal OS permissions. `.gitignore` is an accident-prevention measure, not a data-loss-prevention product.

Inspection omits arguments, raw receipts and callback exception text, but it still exposes identifiers and tool names. Do not treat it as anonymization. There is no authentication, tenant isolation, encrypted storage, quota management, retention policy or tamper-proof audit trail.

## Availability and deployment limits

SQLite coordinates connections sharing the same intact local database. The design does not coordinate separate database copies, a restored older backup, network partitions, hostile writers, unsupported shared filesystems or deleted state. Pending claims can be orphaned even if the callback never started: conservative blocking is intentional. No mechanism interrupts a callback that hangs. This is a synchronous educational prototype, not a hosted service, framework patch, production reliability guarantee or exactly-once execution system.

Unit tests exercise the documented local behavior and simulated failure windows. They do not reproduce or validate the internals of the cited frameworks, prove external delivery, or establish real-world incident reductions.

## Authorship and reuse

The implementation and tests were written for this project. Only source links and short original paraphrases of public discussions are included. No issue code, proprietary implementations, downloaded assets, external datasets or third-party runtime packages are bundled. CI references GitHub-maintained actions by immutable commit; those execute in GitHub's environment under their own upstream terms.

No open-source license is assigned in this initial portfolio release. Public visibility permits viewing through the hosting platform; it should not be represented as an unrestricted reuse license. Dependencies or a license grant should be considered explicitly before wider distribution.
