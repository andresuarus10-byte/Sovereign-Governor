#!/usr/bin/env python3
"""
BRAIDKIT — v0.1
===============
The hash-manifest maker, verifier, and ferry-formatter — the ritual the
braid performs by hand forty times a week, formalized into three
commands. Pure Python 3 stdlib; Pydroid 3 + desktop.

Canon sentence
--------------
braidkit describes bytes and verifies bytes. It grants nothing,
executes nothing, and never modifies the files it manifests. A manifest
is a description; a verification is a receipt; neither is a crown.

House format
------------
MANIFEST.json mirrors the estate's existing handoff manifests
(created_utc / artifact / status / entries[{filename, sha256}]).
SHA256SUMS.txt is standard `sha256sum` format, checkable anywhere with
`sha256sum -c SHA256SUMS.txt`. Ferry zips are deterministic (fixed
timestamps, sorted names, stored uncompressed) so the same bytes always
yield the same anchor.

Commands
--------
  python3 braidkit.py manifest FILE [FILE...] [--artifact NAME]
                      [--status TEXT] [--out DIR]
  python3 braidkit.py verify   MANIFEST.json [--root DIR]
  python3 braidkit.py ferry    FILE [FILE...] [--artifact NAME]
                      [--zip OUT.zip]
  python3 braidkit.py selftest
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BRAIDKIT_VERSION = "braidkit v0.1"
DEFAULT_STATUS = "FERRY_DESCRIBES_GRANTS_NOTHING"
ZIP_EPOCH = (2026, 1, 1, 0, 0, 0)   # fixed: determinism over sentiment


def utcdate() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_entries(paths: list[Path]) -> list[dict]:
    entries = []
    for p in sorted(paths, key=lambda x: x.name):
        if not p.is_file():
            raise FileNotFoundError(f"not a file: {p}")
        entries.append({"filename": p.name, "sha256": sha256_file(p),
                        "bytes": p.stat().st_size})
    names = [e["filename"] for e in entries]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate basenames in manifest set: {names}")
    return entries


def manifest_doc(entries: list[dict], artifact: str, status: str) -> dict:
    return {
        "created_utc": utcdate(),
        "artifact": artifact,
        "status": status,
        "tool": BRAIDKIT_VERSION,
        "entries": [{"filename": e["filename"], "sha256": e["sha256"]}
                    for e in entries],
    }


def sums_text(entries: list[dict]) -> str:
    return "".join(f"{e['sha256']}  {e['filename']}\n" for e in entries)


def bundle_hash(entries: list[dict]) -> str:
    """sha256 of the SHA256SUMS body — one anchor for the whole set."""
    return sha256_bytes(sums_text(entries).encode())


def ferry_block(entries: list[dict], artifact: str,
                zip_info: tuple[str, str, int] | None = None) -> str:
    total = sum(e["bytes"] for e in entries)
    lines = ["=== BRAID FERRY ===",
             f"artifact : {artifact}",
             f"created  : {utcdate()}  ({BRAIDKIT_VERSION})",
             f"files    : {len(entries)}   total bytes: {total}",
             ""]
    for e in entries:
        lines.append(f"{e['sha256']}  {e['bytes']:>9}  {e['filename']}")
    lines += ["",
              f"bundle_sha256 (of SHA256SUMS body): {bundle_hash(entries)}"]
    if zip_info:
        name, zhash, zbytes = zip_info
        lines.append(f"zip anchor: {zhash}  {zbytes} bytes  {name}")
    lines += ["verify: python3 braidkit.py verify MANIFEST.json "
              "[--root DIR]   or: sha256sum -c SHA256SUMS.txt",
              "This ferry describes bytes; it grants nothing.",
              "=== END FERRY ==="]
    return "\n".join(lines)


def write_zip(out: Path, paths: list[Path], entries: list[dict],
              artifact: str, status: str) -> tuple[str, int]:
    doc = manifest_doc(entries, artifact, status)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        def put(name: str, data: bytes):
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
        for p in sorted(paths, key=lambda x: x.name):
            put(p.name, p.read_bytes())
        put("MANIFEST.json", json.dumps(doc, indent=2).encode())
        put("SHA256SUMS.txt", sums_text(entries).encode())
    return sha256_file(out), out.stat().st_size


def cmd_manifest(args) -> int:
    paths = [Path(f) for f in args.files]
    entries = build_entries(paths)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    doc = manifest_doc(entries, args.artifact, args.status)
    (outdir / "MANIFEST.json").write_text(json.dumps(doc, indent=2))
    (outdir / "SHA256SUMS.txt").write_text(sums_text(entries))
    print(f"wrote {outdir / 'MANIFEST.json'} and "
          f"{outdir / 'SHA256SUMS.txt'}")
    print(f"bundle_sha256: {bundle_hash(entries)}")
    return 0


def cmd_verify(args) -> int:
    mpath = Path(args.manifest)
    root = Path(args.root) if args.root else mpath.parent
    try:
        doc = json.loads(mpath.read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read manifest: {exc}")
        return 2
    ok = missing = changed = 0
    for e in doc.get("entries", []):
        p = root / e["filename"]
        if not p.is_file():
            print(f"MISSING  {e['filename']}")
            missing += 1
            continue
        h = sha256_file(p)
        if h == e["sha256"]:
            print(f"OK       {e['filename']}")
            ok += 1
        else:
            print(f"CHANGED  {e['filename']}")
            print(f"         expected {e['sha256']}")
            print(f"         actual   {h}")
            changed += 1
    total = ok + missing + changed
    verdict = "VERIFIED" if total and not (missing or changed) else "FAILED"
    print(f"{verdict}: {ok}/{total} ok, {changed} changed, "
          f"{missing} missing  (artifact: {doc.get('artifact', '?')})")
    return 0 if verdict == "VERIFIED" else 1


def cmd_ferry(args) -> int:
    paths = [Path(f) for f in args.files]
    entries = build_entries(paths)
    zip_info = None
    if args.zip:
        zhash, zbytes = write_zip(Path(args.zip), paths, entries,
                                  args.artifact, args.status)
        zip_info = (Path(args.zip).name, zhash, zbytes)
    print(ferry_block(entries, args.artifact, zip_info))
    return 0


def cmd_selftest(args) -> int:
    import tempfile
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        passed, failed = passed + cond, failed + (not cond)
        print(("  PASS " if cond else "  FAIL ") + name)

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        a, b = d / "a.txt", d / "b.txt"
        a.write_text("alpha\n")
        b.write_text("beta\n")
        entries = build_entries([a, b])
        doc = manifest_doc(entries, "selftest", DEFAULT_STATUS)
        (d / "MANIFEST.json").write_text(json.dumps(doc))
        rc = cmd_verify(argparse.Namespace(
            manifest=str(d / "MANIFEST.json"), root=str(d)))
        check("clean set VERIFIED (rc 0)", rc == 0)
        b.write_text("beta MUTATED\n")
        rc = cmd_verify(argparse.Namespace(
            manifest=str(d / "MANIFEST.json"), root=str(d)))
        check("mutation FAILED (rc 1)", rc == 1)
        b.write_text("beta\n")
        z1, z2 = d / "f1.zip", d / "f2.zip"
        h1, _ = write_zip(z1, [a, b], entries, "selftest", DEFAULT_STATUS)
        h2, _ = write_zip(z2, [a, b], entries, "selftest", DEFAULT_STATUS)
        check("deterministic zip (same bytes, same anchor)", h1 == h2)
        with zipfile.ZipFile(z1) as z:
            names = set(z.namelist())
        check("zip carries MANIFEST + SHA256SUMS",
              {"MANIFEST.json", "SHA256SUMS.txt"} <= names)
        block = ferry_block(entries, "selftest")
        check("ferry block carries bundle anchor",
              bundle_hash(entries) in block)
    print(("SELFTEST PASS (%d checks)" % passed) if not failed
          else ("SELFTEST FAIL (%d of %d)" % (failed, passed + failed)))
    return 0 if not failed else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("command",
                    choices=["manifest", "verify", "ferry", "selftest"])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--artifact", default="unnamed bundle")
    ap.add_argument("--status", default=DEFAULT_STATUS)
    ap.add_argument("--out", default=".")
    ap.add_argument("--zip", default=None)
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    if args.command == "verify":
        if not args.files:
            print("verify needs a MANIFEST.json path")
            return 2
        args.manifest = args.files[0]
        return cmd_verify(args)
    if args.command in ("manifest", "ferry") and not args.files:
        print(f"{args.command} needs at least one file")
        return 2
    return {"manifest": cmd_manifest, "ferry": cmd_ferry,
            "selftest": cmd_selftest}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
