# Why guard the tool boundary?

An agent can lose a response after an action has already happened. Retrying the reasoning workflow is then different from safely repeating the action. Effect Ledger explores this boundary with a deliberately small local prototype, not another agent framework.

## Reports that motivated the project

- [LangGraph issue #9185](https://github.com/langchain-ai/langgraph/issues/9185), opened October 4, 2026, describes a local reproduction in which a fake provider commits an action, its response times out, and resuming the failed tool node repeats the action. The issue was shown as **closed as not planned** when reviewed. This is a reported integration boundary, not evidence that every current LangGraph deployment duplicates actions.
- [LangGraph issue #7417](https://github.com/langchain-ai/langgraph/issues/7417), opened April 5, 2026, reports long-running tool calls being dispatched again while the original is still running. A September 18 update from the original reporter describes moving to a different background-job architecture. The issue was shown as **open**. This is an account of observed symptoms, not an independently established scheduler root cause.
- [A community discussion in r/LangChain](https://www.reddit.com/r/LangChain/comments/1u4zyd2/has_your_langchain_agent_ever_doublefired_a_side/) describes a customer email sent twice after a crash and restart. Replies distinguish workflow checkpoints from external commitment receipts and discuss explicit operation identities and outboxes. These are anecdotal reports and suggestions, not controlled measurements.
- [CrewAI issue #5802](https://github.com/crewAIInc/crewAI/issues/5802), opened May 14, 2026, reports repeated side effects when tasks retry. It was shown as **open**. The reporter also promotes a related implementation, and several comments are commercial pitches; this source is corroborating discussion, not independent product validation.

All four pages were opened and read for this build on October 22, 2026. Research content is paraphrased and linked: no issue reproduction code, comments dataset, personal identities, or third-party assets are bundled.

## What those reports justify building

The recurring user need is to preserve action identity across retries and process restarts. The prototype therefore persists a claim **before** calling a tool, binds the operation to its tool and argument digest, returns stored receipts for completed operations, and blocks unresolved operations. Identical arguments alone must not collapse two intentionally separate actions.

A local ledger cannot atomically commit a remote email or payment and its own receipt. Rather than hide that gap behind an “exactly once” promise, this project deliberately stops after uncertainty. That trades availability for refusing automatic duplicate execution under the same identity. Provider-side idempotency and authoritative reconciliation are future integration requirements.

## Portfolio progression

[Context Pocket](https://github.com/enchantered/context-pocket-2026-10-21) explores recoverable source context; that repository may require account access. [Eval Gate](https://github.com/enchantered/eval-gate) adds offline output and evidence checks with bounded async attempts. Effect Ledger adds **durable state at the tool-effect boundary**. It is not wired into those earlier projects and does not change their code.

This advances the flexible themes of Python foundations, tool calling, state, evaluation, observability and guardrails. It does not claim model quality, a live agent deployment, multi-agent orchestration, authenticated approval, or production readiness. The repeated reports justify an engineering experiment; they do not establish market size, incident prevalence, customer demand for this implementation, or superiority over existing tools.
