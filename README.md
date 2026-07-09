# Sovereign Governor

A tiny, dependency-free gatekeeper that sits between you and a local LLM and
makes it prove it should be allowed to act — *before* it acts.

Pure Python 3 standard library. One file for the gate (`governor.py`), one for
the toolkit (`braidkit.py`). Runs on a phone (Pydroid), a laptop, or a server,
unchanged.

## The idea in one line
**Receipts before capabilities:** nothing is permitted to act until its receipt
is written to disk, nothing reaches past your LAN, and relevance never grants
authority.

## How it flows
```
  you / your app
        |
        v
   +-------------+   ledger write happens BEFORE the model call
   |  GOVERNOR   |-->  (receipt on disk, hash-chained)
   +-------------+
    |    |     |
    |    |     +-->  ask  -> local LLM (llama.cpp / Ollama)   [LAN only]
    |    |
    |    +--------->  act  -> authority table -> grant / HOLD / deny
    |                        (decision only; nothing actuates in v0.1)
    |
    +--------------> every path recorded in the append-only ledger

  There is NO direct model -> tools path. The model never acts; it asks
  the Governor, and the Governor answers to the ledger.
```

## What it does
- Sits in front of any local OpenAI-compatible server (llama.cpp, Ollama, vLLM…).
- Writes every exchange to a hash-chained, append-only ledger *before* the model
  is contacted. Tamper the log and the chain visibly breaks.
- Gates real-world actions through a machine-readable **authority table** (the
  "α-table"): if a capability isn't explicitly listed, it's denied.
- Ships with a HOLD switch and a kill file. If the ledger can't be written,
  permissions collapse to announce-only.
- Never phones the cloud: the source scans *itself* for forbidden remote-endpoint
  tokens (stored reversed so the scanner doesn't flag its own list). 32 self-tests.

## DO NOT use this for
Read this first. The Governor is a governance/audit layer, **not a security
boundary**:
- **Not a sandbox or jail** - it does not contain a compromised model or stop
  code from doing what the OS already allows.
- **Not a firewall** - "LAN-only" is enforced in this process's own calls, not
  system-wide.
- **Not protection against someone who can edit the files** - the hash chain
  makes tampering *visible*, not impossible.
- **Not for broker/trading automation** - there is no order/execution code here,
  by design and by self-scan, and none should be added.
- **Not for child-safety-critical automation.**
- **Not for unattended physical devices** - v0.1 actuates nothing on purpose.
- **Not a vault for cloud secrets** - it holds none and calls no cloud.

This is v0.1, "first light" - a design to discuss and audit, not a safety
guarantee. Longer version in **SCOPE.md**.

`braidkit` is the little sibling — manifest · verify · ferry: deterministic file
bundles with stable SHA-256 anchors, for moving work between machines (or between
AI sessions) with receipts.

## 60-second start
```
python3 governor.py selftest        # 32 checks
python3 braidkit.py selftest        # 5 checks
python3 governor.py init --dir mynode
# edit mynode/ config, then:
python3 governor.py verify
python3 governor.py serve
```

## Scope (please read before roasting)
See **SCOPE.md** — what this is, and what it deliberately is *not*. Short version:
it's a governance/ledger gate, not a sandbox, not a firewall, not a trading
anything. The threat model is meant to be roasted; that's the point.

## Memory layer
The Governor's memory layer is planned to be built on my **Memory Engine** — a
pure-Python/NumPy framework for persistent, importance-weighted recall:
https://github.com/andresuarus10-byte/memory-engine

## License
MIT © 2026 KaelyrAT
