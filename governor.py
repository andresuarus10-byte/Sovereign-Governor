#!/usr/bin/env python3
"""
SOVEREIGN NODE GOVERNOR — v0.1-skeleton (P1 deliverable, M-Node-2 path)
=======================================================================
Purpose
-------
The thin process that sits between world and model. The Governor, not
the model, is the Node (Sovereign Node Architecture Spec v0.2, section 2).
It routes chat requests to the local inference server, gates every act
against the physical alpha table, holds the HOLD gate, and writes the
ledger BEFORE anything is permitted to move.

Canon sentence
--------------
The Governor forwards governed conversation to a local model and issues
governed decisions about acts. It never actuates anything itself, never
reaches beyond the LAN, never lets relevance (K) grant authority (alpha),
and never permits an act before its receipt is on disk. Reachable is not
authorized, in silicon. Bytes before the act.

Structural invariants (NOT config options)
------------------------------------------
1. GOVERNOR_HAS_NO_HANDS: no shell, no dynamic code paths, no child
   process machinery exists in this file. A reversed-token self-scan
   enforces this at verify time and before serve.
2. LEDGER_BEFORE_AGENCY: the intent receipt is fsynced to disk before
   any upstream forward; the decision receipt is written before any
   ALLOWED is returned to a caller.
3. K_NEVER_GRANTS_ALPHA: K (relevance/reachability) is recorded in
   receipts and never consulted by the authority decision. Selftest
   asserts identical decisions at k=0.0 and k=0.99.
4. LAN_ONLY_NO_CLOUD_PATH: the upstream must be a literal loopback or
   RFC1918/link-local address (or the word localhost). No cloud
   fallback exists as a code path (Spec section 10). Bind is loopback
   unless bind_lan is explicitly true, and that choice is receipted.
5. DEFAULT_DENY_ALPHA: an endpoint absent from the physical alpha
   table, revoked, or malformed is DENIED. An empty table actuates
   nothing. Rows change only via the Family Canon amendment path.
6. NO_SILENT_CROWN: the persona layer and the GAC memory route ship as
   loudly labeled placeholders. Their status rides in every receipt.
7. ACTS_ARE_DECISIONS_ONLY (v0.1): zero actuators are wired. /act
   returns a governed decision plus a receipt id; nothing moves.

Failure law (Spec section 10, implemented)
------------------------------------------
Ledger unavailable -> the Node may answer simple local questions but
may not act; all alpha grades collapse to T0 until the ledger writes
again. Chat receipts are buffered in RAM (flagged buffered:true with
their true occurrence time) and flushed on recovery. Governor down ->
models unreachable by design: the Governor is the only route.

Provisional mappings awaiting Family Canon ratification (flagged)
-----------------------------------------------------------------
G-M1: streaming is forced off (stream=false rewritten, receipted).
      Receipts require complete exchanges. Ratify, or a future
      receipted-streaming design replaces this.
G-M2: HOLD scope = every /act request returns HELD; /v1 chat continues
      (observe/answer/log is Tier 0). Ratify or widen HOLD to chat.
G-M3: ledger-degraded mode allows T0 only, buffers receipts in RAM.
      A crash while degraded loses buffered receipts (they are flagged
      as a gap by the seq jump). Ratify or demand secondary spool.
G-M4: quiet-hours behavior "silent" is treated as deny in v0.1 (no
      volume concept exists yet). Ratify or re-map when voice lands.
G-M5: requires_parent_present / requires_verbal_confirm cannot be
      VERIFIED in v0.1; rows requiring them resolve HELD, never
      ALLOWED, until a verified channel exists. Attestations are
      recorded, not trusted.

Environment: pure Python 3 stdlib. Pydroid 3 + desktop + the Brain.

Commands
--------
  python3 governor.py init      [--dir NODE_DIR]
  python3 governor.py serve     [--dir NODE_DIR]
  python3 governor.py status    [--dir NODE_DIR]
  python3 governor.py verify    [--dir NODE_DIR]
  python3 governor.py hold      [--dir NODE_DIR] --reason TEXT
  python3 governor.py release   [--dir NODE_DIR]
  python3 governor.py grant     [--dir NODE_DIR] --endpoint ID
                                --capability CAP [--scope per_action|until]
                                [--expires ISO8601Z]
  python3 governor.py revoke    [--dir NODE_DIR] --grant-id ID
  python3 governor.py selftest
"""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GOVERNOR_VERSION = "governor v0.1-skeleton"
PERSONA_STATUS = "PLACEHOLDER_NOT_CANON"
MEM_STATUS = "PLACEHOLDER_NOT_CANON (GAC route reserved for P2)"
NO_HANDS = True
ALLOWED, HELD, DENIED = "ALLOWED", "HELD", "DENIED"
GRADES = ("T0", "T1lite", "T1full")
MAX_BODY = 1_000_000
SCHEMA_FIELDS = [  # Spec section 8, one row per endpoint, verbatim order
    "endpoint_id", "device_type", "room", "capability", "alpha_grade",
    "allowed_callers", "requires_parent_present", "requires_verbal_confirm",
    "quiet_hours_behavior", "receipt_required", "revocation_status",
]

RED, YEL, GRN, GRY = "\033[91m", "\033[93m", "\033[92m", "\033[90m"
END = "\033[0m"


def paint(color: str, text: str) -> str:
    return f"{color}{text}{END}" if sys.stdout.isatty() else text


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Anti-goblin charm: NO_HANDS self-scan. Tokens stored REVERSED so this
# manifest does not trip its own scanner. Any forward appearance of a
# token in this file's source fails verify and blocks serve.
# ---------------------------------------------------------------------------
_FORBIDDEN_SRC_REVERSED = [
    "ssecorpbus",      # child-process module
    "metsys.so",       # shell-out call on the os module
    "nepop.so",        # pipe-open call on the os module
    "(lave",           # dynamic evaluation call, with paren
    "(cexe",           # dynamic execution call, with paren
    "sepytc",          # foreign-function interface module
    "(__tropmi__",     # dynamic import call, with paren
]


def self_scan(source_path: Path) -> list[str]:
    src = source_path.read_text(errors="replace").lower()
    hits = []
    for rev in _FORBIDDEN_SRC_REVERSED:
        fwd = rev[::-1]
        if fwd in src:
            hits.append(fwd)
    return sorted(set(hits))


# ---------------------------------------------------------------------------
# Ledger: append-only, hash-chained, fsynced. Record schema is
# byte-compatible with the RQC shadow-cockpit ledger so the future
# receiptd daemon can verify both lineages with one verifier.
# ---------------------------------------------------------------------------
class Ledger:
    GENESIS = "0" * 64

    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.path = state_dir / "ledger.jsonl"
        self._lock = threading.Lock()

    def _tip(self) -> tuple[int, str]:
        seq, tip = 0, self.GENESIS
        if self.path.exists():
            with self.path.open() as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        seq, tip = rec["seq"], rec["hash"]
        return seq, tip

    def append(self, kind: str, payload: dict) -> dict:
        with self._lock:
            seq, prev = self._tip()
            rec = {"seq": seq + 1, "ts": utcnow(), "kind": kind,
                   "payload": payload, "prev_hash": prev}
            rec["hash"] = hashlib.sha256(
                (prev + canonical({k: rec[k] for k in
                                   ("seq", "ts", "kind", "payload")})
                 ).encode()).hexdigest()
            with self.path.open("a") as f:
                f.write(canonical(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())   # LEDGER_BEFORE_AGENCY: bytes first
            return rec

    def verify(self) -> tuple[bool, int, str]:
        prev, count = self.GENESIS, 0
        if not self.path.exists():
            return True, 0, self.GENESIS
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                expect = hashlib.sha256(
                    (prev + canonical({k: rec[k] for k in
                                       ("seq", "ts", "kind", "payload")})
                     ).encode()).hexdigest()
                if rec["hash"] != expect or rec["prev_hash"] != prev:
                    return False, count, prev
                prev = rec["hash"]
                count += 1
        return True, count, prev


# ---------------------------------------------------------------------------
# Physical alpha table (Spec section 8) — machine-readable from day one.
# ---------------------------------------------------------------------------
def load_alpha_table(path: Path) -> tuple[dict, list[str]]:
    """Returns (index_by_endpoint_id, problems). Malformed rows are
    excluded from the index (DEFAULT_DENY_ALPHA) and reported."""
    problems: list[str] = []
    index: dict = {}
    if not path.exists():
        return index, [f"alpha table missing: {path}"]
    try:
        doc = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        return index, [f"alpha table unreadable: {exc}"]
    for i, row in enumerate(doc.get("rows", [])):
        missing = [k for k in SCHEMA_FIELDS if k not in row]
        if missing:
            problems.append(f"row {i}: missing fields {missing} — excluded")
            continue
        if row["alpha_grade"] not in GRADES:
            problems.append(f"row {i}: bad alpha_grade "
                            f"{row['alpha_grade']!r} — excluded")
            continue
        index[row["endpoint_id"]] = row
    return index, problems


def in_quiet_hours(cfg: dict, now: datetime | None = None) -> bool:
    q = cfg.get("quiet_hours", {})
    if not q.get("enabled", False):
        return False
    now = now or datetime.now()          # LOCAL time: bedtime is local
    try:
        sh, sm = map(int, q["start"].split(":"))
        eh, em = map(int, q["end"].split(":"))
    except (KeyError, ValueError):
        return False
    cur, start, end = (now.hour, now.minute), (sh, sm), (eh, em)
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end     # window crosses midnight


def live_grant(grants: list[dict], endpoint_id: str,
               capability: str) -> dict | None:
    now = datetime.now(timezone.utc)
    for g in grants:
        if g.get("revoked") or g.get("used_ts"):
            continue
        if g["endpoint_id"] != endpoint_id:
            continue
        if g["capability"] != capability:
            continue
        try:
            if parse_ts(g["expires_ts"]) < now:
                continue
        except (KeyError, ValueError):
            continue
        return g
    return None


def alpha_decision(row: dict | None, req: dict, cfg: dict,
                   hold_reason: str | None, degraded: bool,
                   grants: list[dict]) -> tuple[str, list[str],
                                                dict | None]:
    """The authority decision. NOTE: req may carry 'k'; it is read only
    to be RECORDED by the caller. This function never touches it.
    K_NEVER_GRANTS_ALPHA."""
    reasons: list[str] = []
    if hold_reason is not None:
        return HELD, [f"HOLD engaged ({hold_reason}): ambiguity means "
                      "no action, ask a human (Spec section 2)"], None
    if row is None:
        return DENIED, ["endpoint not present in physical alpha table — "
                        "reachable is not authorized"], None
    grade = row["alpha_grade"]
    if degraded and grade != "T0":
        return DENIED, ["ledger unavailable: all alpha grades collapse "
                        "to T0 until the ledger writes again "
                        "(Spec section 10)"], None
    if str(row["revocation_status"]).lower() != "active":
        return DENIED, [f"endpoint revocation_status is "
                        f"{row['revocation_status']!r}"], None
    if row["capability"] != req.get("capability"):
        return DENIED, [f"capability {req.get('capability')!r} not "
                        f"granted for this endpoint "
                        f"(row grants {row['capability']!r})"], None
    callers = row["allowed_callers"]
    caller = req.get("caller", "")
    if callers != "*" and caller not in callers:
        return DENIED, [f"caller {caller!r} not in allowed_callers"], None
    if in_quiet_hours(cfg):
        behavior = str(row["quiet_hours_behavior"]).lower()
        if behavior in ("deny", "silent"):
            note = "" if behavior == "deny" else " (silent maps to deny, G-M4)"
            return DENIED, [f"quiet hours active{note}"], None
        reasons.append("quiet hours active; row behavior permits")
    attest = req.get("attest", {})
    for field, label in (("requires_parent_present", "parent presence"),
                         ("requires_verbal_confirm", "verbal confirmation")):
        if str(row[field]).lower() in ("y", "yes", "true"):
            asserted = bool(attest.get(field.replace("requires_", ""),
                                       False))
            return HELD, [f"row requires verified {label}; v0.1 cannot "
                          f"verify (caller asserted: {asserted}) — G-M5; "
                          "route through explicit grant with a human "
                          "present"], None
    if grade == "T0":
        reasons.append("Tier-0 standing (observe/answer/log class)")
        return ALLOWED, reasons, None
    if grade == "T1lite":
        reasons.append("Tier-1-lite standing grant; logged; "
                       "parent-revocable")
        return ALLOWED, reasons, None
    g = live_grant(grants, row["endpoint_id"], row["capability"])
    if g is None:
        return HELD, ["Tier-1-full requires an explicit per-action or "
                      "per-scope human grant; none live — holding to a "
                      "human"], None
    reasons.append(f"explicit human grant {g['grant_id']} "
                   f"(scope {g['scope']}, expires {g['expires_ts']})")
    return ALLOWED, reasons, g


# ---------------------------------------------------------------------------
# Upstream validation: LAN_ONLY_NO_CLOUD_PATH
# ---------------------------------------------------------------------------
def validate_upstream(url: str) -> tuple[bool, str]:
    try:
        p = urllib.parse.urlparse(url)
    except ValueError as exc:
        return False, f"unparseable upstream url: {exc}"
    if p.scheme not in ("http", "https"):
        return False, f"upstream scheme {p.scheme!r} not permitted"
    host = p.hostname or ""
    if host == "localhost":
        return True, "localhost"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False, ("upstream host must be a literal loopback/private "
                       "IP or the word localhost — no names that could "
                       "resolve off-LAN (NO_CLOUD_PATH)")
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True, f"{host} ({'loopback' if ip.is_loopback else 'LAN'})"
    return False, f"upstream {host} is not loopback/private — refused"


# ---------------------------------------------------------------------------
# Governor core
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "upstream_url": "http://127.0.0.1:11434/v1/chat/completions",
    "bind_host": "127.0.0.1",
    "bind_port": 8377,
    "bind_lan": False,
    "upstream_timeout_s": 120,
    "models": {"resident": "SET_ME_resident-30b",
               "reflex": "SET_ME_reflex-8b",
               "consult": "SET_ME_consult-70b"},
    "persona": {"enabled": False, "file": "persona.md"},
    "quiet_hours": {"enabled": True, "start": "20:30", "end": "06:30"},
}

EXAMPLE_ALPHA_TABLE = {
    "version": "alpha-table v0.1 EXAMPLE — rows change only via the "
               "Family Canon amendment path; every change is receipted",
    "rows": [
        {"endpoint_id": "desk_speaker_announce", "device_type": "speaker",
         "room": "office", "capability": "speak_announcement",
         "alpha_grade": "T0", "allowed_callers": "*",
         "requires_parent_present": "n", "requires_verbal_confirm": "n",
         "quiet_hours_behavior": "silent", "receipt_required": "y",
         "revocation_status": "active",
         "notes": "Spec section 4 example: announce/speak is Tier-0 standing"},
        {"endpoint_id": "desk_lamp_test", "device_type": "smart_plug",
         "room": "office", "capability": "power_toggle",
         "alpha_grade": "T1lite", "allowed_callers": ["governor_cli"],
         "requires_parent_present": "n", "requires_verbal_confirm": "n",
         "quiet_hours_behavior": "deny", "receipt_required": "y",
         "revocation_status": "revoked",
         "notes": "Ships REVOKED. Flipping to active is P3's first "
                  "reversible act and must itself be receipted."},
        {"endpoint_id": "messages_out_any", "device_type": "comms",
         "room": "house", "capability": "send_message_outside_house",
         "alpha_grade": "T1full", "allowed_callers": [],
         "requires_parent_present": "y", "requires_verbal_confirm": "y",
         "quiet_hours_behavior": "deny", "receipt_required": "y",
         "revocation_status": "revoked",
         "notes": "Ships REVOKED with empty callers: triple-locked until "
                  "the Family Canon says otherwise."},
    ],
}


class Governor:
    def __init__(self, node_dir: Path):
        self.dir = node_dir
        self.state = node_dir / "node_state"
        self.cfg_path = node_dir / "governor_config.json"
        self.alpha_path = node_dir / "alpha_table.json"
        self.grants_path = node_dir / "grants.json"
        self.hold_path = self.state / "HOLD"
        self.cfg = json.loads(self.cfg_path.read_text())
        self.ledger = Ledger(self.state)
        self.alpha, self.alpha_problems = load_alpha_table(self.alpha_path)
        self.degraded = False
        self.buffer: list[tuple[str, dict]] = []   # G-M3 RAM spool
        self._glock = threading.Lock()
        self._force_ledger_fail = False            # selftest hook only

    # -- grants ----------------------------------------------------------
    def load_grants(self) -> list[dict]:
        if self.grants_path.exists():
            return json.loads(self.grants_path.read_text())
        return []

    def save_grants(self, grants: list[dict]) -> None:
        self.grants_path.write_text(json.dumps(grants, indent=1,
                                               sort_keys=True))

    # -- hold --------------------------------------------------------------
    def hold_reason(self) -> str | None:
        if self.hold_path.exists():
            try:
                return json.loads(self.hold_path.read_text()).get(
                    "reason", "unspecified")
            except (ValueError, OSError):
                return "unreadable HOLD file"
        return None

    # -- receipts with section-10 degradation ------------------------------
    def receipt(self, kind: str, payload: dict) -> dict | None:
        """Append a receipt. On ledger failure: enter degraded mode and
        buffer (G-M3). On success after degradation: flush buffer first,
        receipt the recovery, then append."""
        if self._force_ledger_fail:
            self.degraded = True
            self.buffer.append((kind, dict(payload,
                                           buffered_occurred=utcnow())))
            return None
        try:
            if self.degraded and self.buffer:
                spool, self.buffer = self.buffer, []
                for k, p in spool:
                    self.ledger.append(k, dict(p, buffered=True))
                self.degraded = False
                self.ledger.append("ledger_recovered",
                                   {"flushed": len(spool)})
            rec = self.ledger.append(kind, payload)
            self.degraded = False
            return rec
        except OSError as exc:
            self.degraded = True
            self.buffer.append((kind, dict(payload,
                                           buffered_occurred=utcnow(),
                                           ledger_error=str(exc))))
            return None

    # -- the act gate --------------------------------------------------------
    def gate_act(self, req: dict) -> dict:
        grants = self.load_grants()
        row = self.alpha.get(req.get("endpoint_id", ""))
        decision, reasons, used = alpha_decision(
            row, req, self.cfg, self.hold_reason(), self.degraded, grants)
        k = req.get("k", None)
        reasons.append(f"K observed ({k!r}) and recorded; "
                       "K never grants alpha")
        payload = {"decision": decision, "endpoint_id":
                   req.get("endpoint_id"), "capability":
                   req.get("capability"), "caller": req.get("caller"),
                   "k_recorded": k, "attest": req.get("attest", {}),
                   "reasons": reasons,
                   "grade": row["alpha_grade"] if row else None,
                   "degraded": self.degraded}
        if used is not None and decision == ALLOWED:
            with self._glock:
                grants = self.load_grants()
                for g in grants:
                    if g["grant_id"] == used["grant_id"]:
                        if g["scope"] == "per_action":
                            g["used_ts"] = utcnow()
                self.save_grants(grants)
            self.receipt("grant_consumed", {"grant_id": used["grant_id"]})
        rec = self.receipt("act_decision", payload)   # bytes BEFORE reply
        if rec is None and decision == ALLOWED and payload["grade"] != "T0":
            # belt and suspenders: never permit unreceipted non-T0
            decision = DENIED
            reasons.append("receipt write failed at decision time; "
                           "non-T0 permission withdrawn")
        return {"decision": decision, "reasons": reasons,
                "receipt": (rec or {}).get("hash", "BUFFERED_DEGRADED"),
                "actuation": "none — the governor issues decisions, "
                             "not motion (v0.1)"}

    # -- the chat gate ------------------------------------------------------
    def gate_chat(self, body: bytes) -> tuple[int, bytes, dict]:
        try:
            req = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return 400, canonical({"error": "body is not JSON"}).encode(), {}
        notes = []
        if req.get("stream"):
            req["stream"] = False
            notes.append("stream_forced_false (G-M1)")
        requested = req.get("model", "")
        roles = self.cfg.get("models", {})
        routed = roles.get(requested, requested)
        if requested in roles:
            req["model"] = routed
            notes.append(f"role_routed:{requested}")
        else:
            notes.append("model_passthrough")
        persona = self.cfg.get("persona", {})
        if persona.get("enabled"):
            pfile = self.dir / persona.get("file", "persona.md")
            if pfile.exists():
                msgs = req.get("messages", [])
                msgs.insert(0, {"role": "system",
                                "content": pfile.read_text()})
                req["messages"] = msgs
                notes.append("persona_applied_UNRATIFIED "
                             "(flagged, not crowned)")
        out = canonical(req).encode()
        intent = self.receipt("chat_intent", {
            "endpoint": "/v1/chat/completions",
            "model_requested": requested, "model_routed": req.get("model"),
            "request_sha256": sha256_bytes(out), "request_bytes": len(out),
            "persona": PERSONA_STATUS, "notes": notes,
            "hold": self.hold_reason()})
        # G-M2: chat proceeds under HOLD (Tier 0); acts do not.
        t0 = time.time()
        try:
            http_req = urllib.request.Request(
                self.cfg["upstream_url"], data=out,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(
                    http_req,
                    timeout=self.cfg.get("upstream_timeout_s", 120)) as r:
                resp = r.read()
                code = r.status
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            self.receipt("chat_outcome", {
                "intent_hash": (intent or {}).get("hash"),
                "error": exc.__class__.__name__,
                "latency_ms": int((time.time() - t0) * 1000)})
            msg = canonical({"error": "upstream unreachable",
                             "governor_note": "the Governor is the only "
                             "route; if the model is down, silence is "
                             "the lawful answer"}).encode()
            return 502, msg, {"X-Governor-Ledger":
                              "DEGRADED" if self.degraded else "OK"}
        self.receipt("chat_outcome", {
            "intent_hash": (intent or {}).get("hash"),
            "status_code": code, "response_sha256": sha256_bytes(resp),
            "response_bytes": len(resp),
            "latency_ms": int((time.time() - t0) * 1000)})
        return code, resp, {"X-Governor-Ledger":
                            "DEGRADED" if self.degraded else "OK"}

    def status(self) -> dict:
        ok, count, tip = self.ledger.verify()
        grades: dict = {}
        for r in self.alpha.values():
            grades[r["alpha_grade"]] = grades.get(r["alpha_grade"], 0) + 1
        live = [g for g in self.load_grants()
                if not g.get("revoked") and not g.get("used_ts")]
        return {"governor": GOVERNOR_VERSION, "persona": PERSONA_STATUS,
                "memory_route": MEM_STATUS, "no_hands": NO_HANDS,
                "hold": self.hold_reason(), "degraded": self.degraded,
                "buffered_receipts": len(self.buffer),
                "ledger": {"receipts": count, "chain_ok": ok,
                           "tip": tip[:16] + "…"},
                "alpha_rows_by_grade": grades,
                "alpha_problems": self.alpha_problems,
                "grants_live": len(live)}


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
def make_handler(gov: Governor):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SovereignGovernor/0.1"

        def log_message(self, fmt, *args):
            sys.stderr.write(f"[{utcnow()}] {self.address_string()} "
                             f"{fmt % args}\n")

        def _send(self, code: int, body: bytes,
                  extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Governor", GOVERNOR_VERSION)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> bytes | None:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                self._send(413, canonical(
                    {"error": f"body over {MAX_BODY} bytes"}).encode())
                return None
            return self.rfile.read(n)

        def do_GET(self):
            if self.path == "/status":
                self._send(200, canonical(gov.status()).encode())
            elif self.path == "/governor/alpha":
                self._send(200, canonical(
                    {"rows": list(gov.alpha.values()),
                     "problems": gov.alpha_problems}).encode())
            else:
                self._send(404, canonical({"error": "unknown path"}).encode())

        def do_POST(self):
            body = self._body()
            if body is None:
                return
            if self.path == "/v1/chat/completions":
                code, resp, extra = gov.gate_chat(body)
                self._send(code, resp, extra)
            elif self.path == "/act":
                try:
                    req = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._send(400, canonical(
                        {"error": "body is not JSON"}).encode())
                    return
                self._send(200, canonical(gov.gate_act(req)).encode())
            elif self.path == "/mem/propose":
                gov.receipt("mem_proposal", {
                    "status": MEM_STATUS, "resolution": "ABSTAIN",
                    "body_sha256": sha256_bytes(body)})
                self._send(200, canonical({
                    "resolution": "ABSTAIN",
                    "note": "GAC memory governance arrives in P2; the "
                            "route is reserved; ABSTAIN is the only "
                            "lawful answer a placeholder may give "
                            "(No Silent Crown)"}).encode())
            else:
                self._send(404, canonical({"error": "unknown path"}).encode())
    return Handler


def start_server(gov: Governor, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(gov))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def guard_or_die(gov: Governor) -> None:
    hits = self_scan(Path(__file__))
    if hits:
        gov.receipt("governance_breach",
                    {"reason": "forbidden tokens in source",
                     "tokens": hits})
        print(paint(RED, f"GOVERNANCE BREACH: forbidden tokens in "
                         f"source: {hits}. Halted."))
        sys.exit(3)


def cmd_init(args) -> int:
    d = Path(args.dir)
    d.mkdir(parents=True, exist_ok=True)
    wrote = []
    for name, obj in (("governor_config.json", DEFAULT_CONFIG),
                      ("alpha_table.json", EXAMPLE_ALPHA_TABLE),
                      ("grants.json", [])):
        p = d / name
        if p.exists():
            print(f"refusing to overwrite existing {p}")
            continue
        p.write_text(json.dumps(obj, indent=2))
        wrote.append(name)
    print(f"wrote: {wrote or 'nothing (all present)'} in {d}/")
    print("edit governor_config.json (upstream + model names), review "
          "alpha_table.json, then: governor.py verify, governor.py serve")
    return 0


def cmd_serve(args) -> int:
    gov = Governor(Path(args.dir))
    guard_or_die(gov)
    ok, why = validate_upstream(gov.cfg["upstream_url"])
    if not ok:
        gov.receipt("governance_breach", {"reason": why})
        print(paint(RED, f"REFUSED: {why}"))
        return 3
    host = gov.cfg.get("bind_host", "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost") and not \
            gov.cfg.get("bind_lan", False):
        print(paint(RED, "REFUSED: non-loopback bind without "
                         "bind_lan=true in config"))
        return 3
    lock = gov.state / "governor.lock"
    if lock.exists():
        print(paint(YEL, f"lock file exists ({lock}); another governor "
                         f"may be running. Delete it if stale."))
        return 2
    lock.write_text(canonical({"pid": os.getpid(), "ts": utcnow()}))
    gov.receipt("governor_start", {
        "version": GOVERNOR_VERSION,
        "config_sha256": sha256_file(gov.cfg_path),
        "alpha_table_sha256": sha256_file(gov.alpha_path),
        "upstream": gov.cfg["upstream_url"], "upstream_class": why,
        "bind": f"{host}:{gov.cfg['bind_port']}",
        "bind_lan": bool(gov.cfg.get("bind_lan")),
        "persona": PERSONA_STATUS, "no_hands_scan": "CLEAN",
        "alpha_problems": gov.alpha_problems})
    print(f"{GOVERNOR_VERSION} on {host}:{gov.cfg['bind_port']} -> "
          f"{gov.cfg['upstream_url']} ({why})")
    print("the Governor is the only route: if it is down, the models "
          "are unreachable by design. Ctrl-C to stop.")
    server = ThreadingHTTPServer((host, int(gov.cfg["bind_port"])),
                                 make_handler(gov))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        gov.receipt("governor_stop", {"buffered_lost": len(gov.buffer)})
        lock.unlink(missing_ok=True)
        server.server_close()
    return 0


def cmd_status(args) -> int:
    gov = Governor(Path(args.dir))
    s = gov.status()
    scan = self_scan(Path(__file__))
    print(f"governor : {s['governor']}")
    print(f"persona  : {s['persona']}")
    print(f"memory   : {s['memory_route']}")
    print(f"no_hands : {NO_HANDS}  (source scan: "
          f"{'CLEAN' if not scan else scan})")
    hold = s["hold"]
    print(f"hold     : {paint(RED, hold) if hold else 'clear'}")
    print(f"ledger   : {s['ledger']['receipts']} receipts, chain "
          f"{'OK' if s['ledger']['chain_ok'] else paint(RED, 'BROKEN')}, "
          f"tip {s['ledger']['tip']}")
    print(f"alpha    : {s['alpha_rows_by_grade'] or 'EMPTY (deny-all)'}"
          f"{'  problems: ' + str(s['alpha_problems']) if s['alpha_problems'] else ''}")
    print(f"grants   : {s['grants_live']} live")
    return 0


def cmd_verify(args) -> int:
    gov = Governor(Path(args.dir))
    ok, count, tip = gov.ledger.verify()
    scan = self_scan(Path(__file__))
    up_ok, up_why = validate_upstream(gov.cfg["upstream_url"])
    print(f"receipts    : {count}")
    print(f"chain       : {'INTACT' if ok else 'BROKEN at record ' + str(count + 1)}")
    print(f"tip         : {tip}")
    print(f"source scan : {'CLEAN (no hands)' if not scan else scan}")
    print(f"alpha table : {len(gov.alpha)} valid rows"
          f"{'; problems: ' + str(gov.alpha_problems) if gov.alpha_problems else ''}")
    print(f"upstream    : {'OK ' + up_why if up_ok else 'REFUSED — ' + up_why}")
    print(f"config sha  : {sha256_file(gov.cfg_path)}")
    print(f"alpha sha   : {sha256_file(gov.alpha_path)}")
    all_ok = ok and not scan and up_ok and not gov.alpha_problems
    return 0 if all_ok else 1


def cmd_hold(args) -> int:
    gov = Governor(Path(args.dir))
    gov.hold_path.write_text(canonical({"ts": utcnow(),
                                        "reason": args.reason}))
    gov.receipt("hold_engaged", {"reason": args.reason})
    print(paint(YEL, f"HOLD engaged: {args.reason}"))
    return 0


def cmd_release(args) -> int:
    gov = Governor(Path(args.dir))
    if gov.hold_reason() is None:
        print("no HOLD engaged.")
        return 0
    try:
        ans = input("type 'release hold' to confirm: ").strip().lower()
    except EOFError:
        ans = ""
    if ans != "release hold":
        print("not confirmed; HOLD remains.")
        return 1
    gov.hold_path.unlink(missing_ok=True)
    gov.receipt("hold_released", {"by": "human"})
    print("HOLD released.")
    return 0


def cmd_grant(args) -> int:
    gov = Governor(Path(args.dir))
    if args.scope == "until" and not args.expires:
        print("scope 'until' requires --expires ISO8601Z")
        return 1
    expires = args.expires or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    if args.scope == "per_action" and not args.expires:
        expires = (datetime.now(timezone.utc)
                   .replace(microsecond=0))
        expires = (expires.timestamp() + 900)
        expires = datetime.fromtimestamp(
            expires, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        ans = input(f"grant {args.scope} on {args.endpoint}/"
                    f"{args.capability} until {expires} — type 'grant' "
                    f"to confirm: ").strip().lower()
    except EOFError:
        ans = ""
    if ans != "grant":
        print("not confirmed; nothing granted.")
        return 1
    g = {"grant_id": hashlib.sha256(
            f"{args.endpoint}{args.capability}{utcnow()}".encode()
         ).hexdigest()[:12],
         "endpoint_id": args.endpoint, "capability": args.capability,
         "scope": args.scope, "expires_ts": expires,
         "granted_ts": utcnow(), "revoked": False}
    grants = gov.load_grants()
    grants.append(g)
    gov.save_grants(grants)
    gov.receipt("grant_issued", g)
    print(f"grant {g['grant_id']} issued (receipted).")
    return 0


def cmd_revoke(args) -> int:
    gov = Governor(Path(args.dir))
    grants = gov.load_grants()
    for g in grants:
        if g["grant_id"] == args.grant_id and not g.get("revoked"):
            g["revoked"] = True
            gov.save_grants(grants)
            gov.receipt("grant_revoked", {"grant_id": args.grant_id})
            print(f"grant {args.grant_id} revoked (receipted).")
            return 0
    print("no live grant with that id.")
    return 1


# ---------------------------------------------------------------------------
# Selftest: the battery that must pass before anything is trusted.
# ---------------------------------------------------------------------------
def cmd_selftest(args) -> int:
    import tempfile
    passed = failed = 0

    def check(name: str, cond: bool):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(paint(GRN, f"  PASS {name}"))
        else:
            failed += 1
            print(paint(RED, f"  FAIL {name}"))

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        cmd_init(argparse.Namespace(dir=str(d)))
        gov = Governor(d)

        print("· ledger")
        r1 = gov.ledger.append("t", {"a": 1})
        gov.ledger.append("t", {"a": 2})
        ok, n, _ = gov.ledger.verify()
        check("chain verifies", ok and n >= 2 and r1["seq"] >= 1)
        raw = gov.ledger.path.read_text()
        gov.ledger.path.write_text(raw.replace('"a":1', '"a":9', 1))
        ok2, _, _ = gov.ledger.verify()
        check("tamper detected", not ok2)
        gov.ledger.path.write_text(raw)

        print("· alpha table")
        base = {"caller": "governor_cli", "attest": {}}
        r = gov.gate_act(dict(base, endpoint_id="ghost",
                              capability="anything"))
        check("unknown endpoint DENIED", r["decision"] == DENIED)
        r = gov.gate_act(dict(base, endpoint_id="desk_speaker_announce",
                              capability="speak_announcement"))
        quiet = in_quiet_hours(gov.cfg)
        check("T0 announce " + ("DENIED in quiet hours" if quiet
                                else "ALLOWED"),
              r["decision"] == (DENIED if quiet else ALLOWED))
        r = gov.gate_act(dict(base, endpoint_id="desk_lamp_test",
                              capability="power_toggle"))
        check("revoked T1lite DENIED", r["decision"] == DENIED)
        # activate the lamp row for deeper tests
        tbl = json.loads(gov.alpha_path.read_text())
        for row in tbl["rows"]:
            row["revocation_status"] = "active"
            row["quiet_hours_behavior"] = "normal"
        tbl["rows"][2]["allowed_callers"] = "*"   # caller lock opens so
        gov.alpha_path.write_text(json.dumps(tbl))  # G-M5 branch is reachable
        gov.alpha, gov.alpha_problems = load_alpha_table(gov.alpha_path)
        r = gov.gate_act(dict(base, endpoint_id="desk_lamp_test",
                              capability="power_toggle"))
        check("active T1lite ALLOWED+receipted",
              r["decision"] == ALLOWED and len(r["receipt"]) == 64)
        r = gov.gate_act(dict(base, endpoint_id="desk_lamp_test",
                              capability="wrong_cap"))
        check("capability mismatch DENIED", r["decision"] == DENIED)
        r = gov.gate_act({"endpoint_id": "desk_lamp_test",
                          "capability": "power_toggle",
                          "caller": "stranger"})
        check("caller not allowed DENIED", r["decision"] == DENIED)
        r = gov.gate_act(dict(base, endpoint_id="messages_out_any",
                              capability="send_message_outside_house",
                              attest={"parent_present": True,
                                      "verbal_confirm": True}))
        check("T1full attestation-required HELD (G-M5)",
              r["decision"] == HELD)

        print("· K never grants alpha")
        lo = gov.gate_act(dict(base, endpoint_id="desk_lamp_test",
                               capability="power_toggle", k=0.0))
        hi = gov.gate_act(dict(base, endpoint_id="desk_lamp_test",
                               capability="power_toggle", k=0.99))
        check("identical decision at k=0.0 vs k=0.99",
              lo["decision"] == hi["decision"] == ALLOWED)
        no = gov.gate_act(dict(base, endpoint_id="ghost",
                               capability="x", k=0.99))
        check("high K cannot rescue unknown endpoint",
              no["decision"] == DENIED)

        print("· grants (T1full)")
        tbl["rows"][2]["requires_parent_present"] = "n"
        tbl["rows"][2]["requires_verbal_confirm"] = "n"
        tbl["rows"][2]["allowed_callers"] = "*"
        gov.alpha_path.write_text(json.dumps(tbl))
        gov.alpha, _ = load_alpha_table(gov.alpha_path)
        r = gov.gate_act(dict(base, endpoint_id="messages_out_any",
                              capability="send_message_outside_house"))
        check("T1full without grant HELD", r["decision"] == HELD)
        far = datetime.fromtimestamp(time.time() + 600, timezone.utc
                                     ).strftime("%Y-%m-%dT%H:%M:%SZ")
        g = {"grant_id": "testgrant0001", "endpoint_id":
             "messages_out_any", "capability":
             "send_message_outside_house", "scope": "per_action",
             "expires_ts": far, "granted_ts": utcnow(), "revoked": False}
        gov.save_grants([g])
        r = gov.gate_act(dict(base, endpoint_id="messages_out_any",
                              capability="send_message_outside_house"))
        check("live grant ALLOWED", r["decision"] == ALLOWED)
        r = gov.gate_act(dict(base, endpoint_id="messages_out_any",
                              capability="send_message_outside_house"))
        check("per_action grant consumed -> HELD again",
              r["decision"] == HELD)

        print("· HOLD")
        gov.hold_path.write_text(canonical({"ts": utcnow(),
                                            "reason": "selftest"}))
        r = gov.gate_act(dict(base, endpoint_id="desk_lamp_test",
                              capability="power_toggle"))
        check("HOLD -> act HELD", r["decision"] == HELD)
        gov.hold_path.unlink()

        print("· ledger-degraded law (Spec section 10 / G-M3)")
        gov._force_ledger_fail = True
        r = gov.gate_act(dict(base, endpoint_id="desk_lamp_test",
                              capability="power_toggle"))
        check("degraded: T1 collapses (DENIED)", r["decision"] == DENIED)
        r = gov.gate_act(dict(base, endpoint_id="desk_speaker_announce",
                              capability="speak_announcement"))
        check("degraded: T0 still ALLOWED (buffered receipt)",
              r["decision"] == ALLOWED and gov.degraded
              and len(gov.buffer) >= 2)
        gov._force_ledger_fail = False
        gov.receipt("selftest_recovery_probe", {})
        ok3, _, _ = gov.ledger.verify()
        txt = gov.ledger.path.read_text()
        check("recovery flushed buffer + chain intact",
              ok3 and not gov.degraded and '"buffered":true' in txt
              and "ledger_recovered" in txt)

        print("· upstream law (LAN only)")
        check("cloud host refused",
              not validate_upstream("https://api.example.com/v1")[0])
        check("loopback accepted",
              validate_upstream("http://127.0.0.1:11434/v1/chat/completions")[0])
        check("RFC1918 accepted",
              validate_upstream("http://192.168.1.20:8000/v1/chat/completions")[0])
        check("bare hostname refused",
              not validate_upstream("http://mybox.lan:8000/v1")[0])

        print("· quiet hours math")
        cfgq = {"quiet_hours": {"enabled": True, "start": "20:30",
                                "end": "06:30"}}
        check("23:00 inside crossing window",
              in_quiet_hours(cfgq, datetime(2026, 7, 6, 23, 0)))
        check("05:00 inside crossing window",
              in_quiet_hours(cfgq, datetime(2026, 7, 6, 5, 0)))
        check("12:00 outside crossing window",
              not in_quiet_hours(cfgq, datetime(2026, 7, 6, 12, 0)))

        print("· no hands")
        check("self scan CLEAN", self_scan(Path(__file__)) == [])
        probe = d / "dirty.txt"
        probe.write_text("ssecorpbus"[::-1] + ".run(x)")
        check("scanner catches a real hand", self_scan(probe) != [])

        print("· end-to-end loopback (stub model + live governor)")
        canned = canonical({"choices": [{"message": {
            "role": "assistant", "content": "stub ok"}}]}).encode()
        ordering = {"intent_on_disk_first": False}

        class Stub(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                txt2 = gov2.ledger.path.read_text()
                ordering["intent_on_disk_first"] = "chat_intent" in txt2
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(canned)))
                self.end_headers()
                self.wfile.write(canned)

        stub = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=stub.serve_forever, daemon=True).start()
        cfg2 = json.loads((d / "governor_config.json").read_text())
        cfg2["upstream_url"] = (f"http://127.0.0.1:{stub.server_port}"
                                f"/v1/chat/completions")
        (d / "governor_config.json").write_text(json.dumps(cfg2))
        gov2 = Governor(d)
        gsrv = start_server(gov2, "127.0.0.1", 0)
        port = gsrv.server_port
        try:
            body = canonical({"model": "resident", "stream": True,
                              "messages": [{"role": "user",
                                            "content": "hello"}]}).encode()
            rq = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(rq, timeout=10) as resp:
                out = resp.read()
                hdr = resp.headers.get("X-Governor-Ledger")
            check("chat forwarded through governor",
                  b"stub ok" in out and hdr == "OK")
            check("LEDGER_BEFORE_AGENCY (intent receipt preceded "
                  "upstream call)", ordering["intent_on_disk_first"])
            txt3 = gov2.ledger.path.read_text()
            check("intent + outcome receipted",
                  "chat_intent" in txt3 and "chat_outcome" in txt3
                  and "stream_forced_false" in txt3)
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/status", timeout=10) as resp:
                st = json.loads(resp.read())
            check("/status live", st["governor"] == GOVERNOR_VERSION)
            rq = urllib.request.Request(
                f"http://127.0.0.1:{port}/mem/propose",
                data=b"{}", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(rq, timeout=10) as resp:
                mem = json.loads(resp.read())
            check("/mem/propose ABSTAINs (No Silent Crown)",
                  mem["resolution"] == "ABSTAIN")
        finally:
            gsrv.shutdown()
            stub.shutdown()

    print()
    verdict = (paint(GRN, f"SELFTEST PASS ({passed} checks)") if not failed
               else paint(RED, f"SELFTEST FAIL ({failed} of "
                               f"{passed + failed})"))
    print(verdict)
    print("a passing selftest is a receipt, not a crown.")
    return 0 if not failed else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("command",
                    choices=["init", "serve", "status", "verify", "hold",
                             "release", "grant", "revoke", "selftest"])
    ap.add_argument("--dir", default="sovereign_node")
    ap.add_argument("--reason", default="unspecified")
    ap.add_argument("--endpoint")
    ap.add_argument("--capability")
    ap.add_argument("--scope", choices=["per_action", "until"],
                    default="per_action")
    ap.add_argument("--expires")
    ap.add_argument("--grant-id", dest="grant_id")
    args = ap.parse_args(argv)
    return {"init": cmd_init, "serve": cmd_serve, "status": cmd_status,
            "verify": cmd_verify, "hold": cmd_hold,
            "release": cmd_release, "grant": cmd_grant,
            "revoke": cmd_revoke, "selftest": cmd_selftest}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
