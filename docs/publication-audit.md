# Public-release safety gate

This candidate starts in a new directory and a new Git history. No existing repository, historical commit, private workspace document, resume, fixture, account configuration or prior author's metadata is imported. The intended repository is `enchantered/effect-ledger`, with public visibility authorized by the owner.

Before publication, the release operator must:

1. Review the complete staged-file inventory and read all project source, tests and documentation. Only original code, synthetic examples and paraphrased evidence links may be included.
2. Scan candidate files with Gitleaks, with redacted output and no custom allowlist. No local database, raw forum extraction, credential file, downloaded asset, vendored package, binary, archive or symlink belongs in the candidate.
3. Commit with handle-only author and committer metadata. Inspect **every reachable commit and blob**, including messages, metadata, paths and all refs, not just the working tree. Check known owner-name indicators, email addresses, credential patterns, private-key material and available environment-secret values without printing those values.
4. Run Gitleaks against reachable Git history as a separate check. Re-scan after any modification or new commit.
5. Resolve licensing questions: this is original code, no external runtime dependency or copied forum reproduction is bundled, and no open-source license is asserted. Linked discussions remain on their original sites under their own terms. Public visibility is not an unrestricted reuse grant.
6. Run unit tests and both offline demos. Inspect that demonstration databases and test artifacts remain untracked.
7. Only after a clean gate, create a **new** public repository, push the audited commit, and compare the remote branch SHA and visibility with the local release. Never repurpose, delete, rewrite or modify an existing repository.

If a safety finding cannot be resolved, stop before publication. Report the category, file path and commit identifier (when applicable), never the sensitive matched text. Automated scanners do not prove that all PII or secrets are absent; manual review and a deliberately narrow file inventory remain necessary.

Audit logs and test outputs are retained outside the repository by the release operator. This document describes the required gate, not a perpetual warranty about later user contributions. GitHub CI status should be reported from an observed run, not inferred from the presence of a workflow file.
