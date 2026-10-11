"""Build a deterministic mod ZIP from the repository's explicit payload."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
MOD = CONFIG["mod"]
VERSION = CONFIG["version"]
REQUIRED = {"single_mod", "settings", "gameplay", "multiplayer", "integration", "installation"}


def payload():
    sources = sorted((ROOT / "Mods" / MOD).rglob("*"))
    result = {}
    for path in sources:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if path.name not in {"enabled.txt"} and path.suffix != ".lua":
            raise ValueError(f"unexpected runtime file: {relative}")
        result[relative] = path.read_bytes()
    for required in [f"Mods/{MOD}/enabled.txt", f"Mods/{MOD}/Scripts/main.lua"]:
        if required not in result:
            raise ValueError(f"missing runtime file: {required}")
    pakdir = ROOT / "Paks"
    paths = sorted(pakdir.iterdir()) if pakdir.exists() else []
    expected = {f"{MOD}_P.{extension}" for extension in ("pak", "utoc", "ucas")} if CONFIG["overlay"] else set()
    if {path.name for path in paths} != expected:
        raise ValueError(f"overlay companions mismatch: expected {sorted(expected)}")
    for path in paths:
        result[f"the_cabin_game/Content/Paks/~mods/{path.name}"] = path.read_bytes()
    return dict(sorted(result.items()))


def fingerprint(files=None):
    files = payload() if files is None else files
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require_acceptance(files=None):
    acceptance = json.loads((ROOT / "acceptance.json").read_text(encoding="utf-8"))
    if acceptance.get("accepted") is not True:
        raise ValueError("game acceptance is pending; release blocked")
    actual = fingerprint(files)
    if acceptance.get("payload_sha256") != actual:
        raise ValueError(f"acceptance payload mismatch: actual {actual}")
    if acceptance.get("game_build") != CONFIG["game_build"] or acceptance.get("ue4ss") != CONFIG["ue4ss"]:
        raise ValueError("accepted game/runtime baseline differs from package")
    checks = acceptance.get("checks", {})
    for name in sorted(REQUIRED):
        check = checks.get(name, {})
        if check.get("passed") is not True or not isinstance(check.get("evidence"), str) or not check["evidence"].strip():
            raise ValueError(f"missing passed acceptance with evidence: {name}")


def contents(candidate=True):
    if not re.fullmatch(r"Cabin[A-Za-z]+", MOD) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", VERSION):
        raise ValueError("invalid package identity or version")
    files = payload()
    if not candidate:
        require_acceptance(files)
    for name in ["README.md", "LICENSE.md", "CHANGELOG.md"]:
        files[name] = (ROOT / name).read_bytes()
    if (ROOT / "profile_templates.json").exists():
        files["profile_templates.json"] = (ROOT / "profile_templates.json").read_bytes()
    manifest = {"mod": MOD, "version": VERSION + ("-candidate" if candidate else ""),
                "game_build": CONFIG["game_build"], "ue4ss": CONFIG["ue4ss"],
                "game_acceptance": not candidate, "payload_sha256": fingerprint(),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return dict(sorted(files.items()))


def build(candidate=True):
    files = contents(candidate)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / f"{MOD}-{VERSION}{'-candidate' if candidate else ''}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in files.items():
            entry = zipfile.ZipInfo(name, (2026, 10, 11, 0, 0, 0))
            entry.create_system = 3
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, data, compresslevel=9)
    verify(archive, candidate)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (dist / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8", newline="\n")
    print(f"info: built {archive.name}; sha256={checksum}; game_acceptance={not candidate}")
    return archive


def verify(archive, candidate=True):
    expected = contents(candidate)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or bundle.namelist() != list(expected):
            raise ValueError("ZIP integrity or file inventory mismatch")
        for name, data in expected.items():
            if bundle.read(name) != data:
                raise ValueError(f"archive differs from source: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    try:
        if args.archive:
            verify(args.archive, not args.release)
            print(f"info: confirmed source parity: {args.archive}")
        else:
            build(not args.release)
    except Exception as error:
        raise SystemExit(f"error: package {MOD}: {error}") from error
