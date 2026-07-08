# SCOPE — what the Sovereign Governor is and is not

## It IS
- A **gate process**: routes requests to a local model and records them.
- A **ledger**: append-only, hash-chained receipts, verifiable with one command.
- An **authority table**: a default-deny list of which real-world actions are
  permitted, and under what conditions.
- A set of **stop controls**: HOLD, a kill file, and ledger-failure →
  announce-only.

## It is NOT
- **Not a sandbox or a jail.** It does not contain a compromised model or stop
  code from doing what the OS allows. It governs *its own* actions, honestly
  recorded.
- **Not a network firewall.** "LAN-only / default-deny outbound" is enforced in
  *this* process's own calls, not system-wide.
- **Not security against a determined local attacker.** Anyone who can edit the
  files or the ledger can change the rules; the hash chain makes tampering
  *visible*, not impossible.
- **Not a trading system.** No broker, order, or execution code exists anywhere,
  by design and by self-scan.
- **Not finished.** v0.1, "first light." For discussion and review.

## Threat model, invited
The interesting question isn't "is this unbreakable" (it isn't). It's whether
receipts-before-capabilities + default-deny authority + visible tamper-evidence
make a locally-run assistant *auditable and constrained enough to trust with
small real-world actions.* Roast that. Issues welcome.
