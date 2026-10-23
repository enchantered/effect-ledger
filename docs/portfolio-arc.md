# From checkable answers to inspectable actions

The portfolio's thread is **recover evidence, check the output, preserve action identity, and make uncertainty visible**. The twelve themes remain a flexible guide, not a claim that every theme is complete.

## Why extend a project instead of opening another repository

The October 23 run began with public issue reports. It then discovered that Effect Ledger had already been built on October 22 after Eval Gate. Rebuilding an idempotency wrapper would duplicate existing work. A focused milestone in the existing repository makes a more coherent portfolio: inspect unresolved actions without changing the ledger or guessing that they failed. The [dated decision](2026-10-23-decision.md) connects that choice to independent reports, current launch/news observations, a survey and paper/patent publications.

The progression is not a strict chronology of prerequisites. Python/async foundations and structured outputs are demonstrated in Eval Gate; local memory and persistence in Context Pocket and ReviewGate remain separate learning experiments. Human-review boundaries were explored early, while authenticated approval and live provider authorization remain unbuilt.

## What the projects actually demonstrate

**Return Window** explores a user-entered CSV-to-calendar handoff. **Occlusion Lab** demonstrates deterministic planning where unknown space must not be treated as confirmed free. These support explicit state and usability; neither is an LLM system.

**Context Pocket** recovers local text with inspectable source locations. It does not import native provider archives, generate answers or provide semantic memory. **Eval Gate** adds async simulation, structured-response checks, exact citation presence and metadata traces. A passing quote check is not answer truth.

**ReviewGate** explores draft persistence and human review. Its optional SDK cases are offline demonstrations, not authenticated enterprise authorization. **Effect Ledger** adds a durable claim before trusted local callbacks, cached receipts and conservative blocking after uncertainty. Today's read-only review makes those blocks inspectable, but does not reconcile, authorize or replay an effect.

These are separate runnable prototypes. There is no live cross-project agent pipeline, provider integration or multi-agent product runtime. Parallel agents assisted this research/build process; that does not make the shipped library a multi-agent system.

## Where the twelve themes stand

Python foundations, async behavior, state, structured contracts, tests and small traces have concrete demonstrations. Tool-effect handling is simulated with a local outbox. LLM fundamentals are reflected in documented limits, not validated live-model quality, cost or token benchmarks.

Single-agent integration remains a sensible next experiment once authorized user failures define its contract. Multi-agent orchestration is deferred because it would add handoffs before the outcome boundary is understood. Human-in-the-loop here means visibility for investigation, not a recorded approval or an authenticated permission check.

Security is narrow: bounded displayed rows, safe parsing, selected metadata omission and explicit no-replay behavior. There is no hostile-process sandbox, encrypted storage, tenant isolation or tamper-proof ledger. Production deployment is not achieved by a public GitHub repository or a configured CI workflow.

Public portfolio publication follows content/history safety checks and handle-only metadata. No open-source license is assigned; public visibility is not an unrestricted reuse grant. The two reference themes of deployment and open source therefore remain only partially explored.

## What would justify the next step

Test whether people distinguish an in-flight action, an uncertain effect and a confirmed receipt without assuming a retry is safe. Compare with their current logs and provider status pages. A future integration should add authoritative read-back and provider-specific idempotency, not a generic force-complete button.

The five older active projects were reviewed and tested this run; no sampled material bug justified a maintenance commit. The separately owned randomized 0–72-hour due ledger remains unavailable. No replacement schedule or activity-only commit was made. Older personal author histories were not imported into this repository or rewritten.
