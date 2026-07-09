# Security policy

## Honest framing
The Sovereign Governor is a governance and audit layer, **not a security
boundary**. Its guarantees are narrow and specific: append-only, hash-chained
receipts that make tampering *visible*; default-deny authority (anything not
listed is refused); and no cloud calls (enforced by a source self-scan). It does
**not** sandbox a compromised model, firewall the host, or resist an attacker who
can already edit the files. See `SCOPE.md` and the "DO NOT use this for" section
of the README.

## Reporting an issue
Threat-model critique is actively welcome - the project invites it.
- Open a GitHub **issue** for anything non-sensitive: design gaps, missed
  assumptions, "reachable-vs-authorized" holes, ledger-integrity edge cases.
- For anything you'd rather not post publicly, open a minimal issue titled
  **"security contact request"** and the maintainer will follow up privately.

Helpful to include: what you tried, what you expected, what happened, and - if
relevant - which invariant you think it violates (no-live-path,
ledger-before-agency, K-never-grants-alpha, HOLD-on-ambiguity).

## Good-faith terms
A personal, early-stage project maintained on break time. No bounty, no SLA -
just honest engagement and public credit for findings that improve it.

## Supported version
v0.1 (first light). Fixes land on `main`; no back-porting yet.
