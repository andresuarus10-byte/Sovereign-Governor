# v0.2 issue ledger

Recorded from a multi-AI ("braid") review of v0.1. None were v0.1
blockers; the first-light kit shipped clean. Each is an additive
enhancement that respects the standing invariants (no-live-path,
ledger-before-agency, K-never-grants-α, HOLD-on-ambiguity). Refinements
are ratified deliberately — receipts before crowns.

## Accepted — build in v0.2
1. **Structured "why" on every receipt.**
   Today refusals/holds record prose reasons. Add a machine-readable
   justification block to act/hold/refuse receipts, e.g.:
       decision: HELD
       law_invoked: [rule_4.2, alpha_grade:T1full, missing_human_grant]
       minimal_justification: "authority absent; no further inference"
   Goal: a future human (or auditor) reads the chain and sees not just
   what happened but which rule fired. Governance logs become
   archaeology within a few years — write for that reader.
   Constraint: additive fields only; existing hash-chain format and
   verification stay byte-stable for prior records.

2. **Menu mode (phone-first).**
   A numbered wrapper over existing commands so nothing needs to be
   memorized on an S21:
       1. status   2. ask   3. act   4. grant   5. revoke
       6. hold/release   7. verify   8. seal
   Constraint: menu invokes the SAME gated code paths — it is a front
   door, never a bypass. No new authority, no shortcut around α/HOLD.

3. **Ledger crash-hardening.**
   fsync after each append; on read, tolerate a torn trailing line
   (detect + report, keep all prior records valid). The chain already
   fails safe (append-only + hash means a partial last line is
   detectable and earlier receipts survive); this makes the guarantee
   explicit and self-healing. Kernel of the braid's "power loss
   mid-receipt" note — the software half of it.

4. **Threat-model table in the repo (not just prose).**
   Promote SCOPE.md's prose into a maintained table so gaps are explicit and
   trackable. Columns: threat | current protection | known gap | planned patch.
   Seed rows to fill honestly (an empty "current protection" cell is a valid,
   useful admission):
       - compromised local model
       - malicious prompt / injection
       - LAN exposure of the model endpoint
       - ledger tampering
       - config / alpha-table edit by a local user
       - power loss mid-write (see item 3)
       - accidental authority grant
       - quiet-hours bypass attempt

## Already roadmapped (review validated the design; no change)
- **Memory discipline** — observations-vs-facts, confidence values,
  provenance ("who suggested this, when"), periodic self-audits. This
  IS the GAC P2 memory-engine port; /mem/propose graduates from
  ABSTAIN then.
- **Four-layer stack** — Model → Reasoning/Persona → Governor →
  Memory/Ledger → Tools. Matches the Node spec; memory lives outside
  the model as infrastructure, which is what makes model-swaps cheap.
- **Persona graduation** — "family canon as resonance, not authority."
  The persona's `UNRATIFIED (flagged, not crowned)` marker is
  deliberate and stays until ratified. Also P2.

## Out of scope for THIS public repo (private-estate / hardware notes)
- UPS + 850W PSU, monthly backup/restore cron with checksum alert,
  ClawStage embodiment adapter stub (`embodiment/clawstage.py`).
  Real advice, but ops/hardware for the Brain — not the governance
  tool. Lives in the private estate, not here.
