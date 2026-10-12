"""Guard unpublished updates and preserve file-to-file dependency ranges."""
from decimal import Decimal
from pathlib import Path
import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request

BASE = "https://api.nexusmods.com/v3"
ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "dist/nexus-draft.json"

def require(condition, message):
    if not condition:
        raise ValueError(message)

def api(method, path, payload=None):
    key = os.environ.get("NEXUSMODS_API_KEY")
    require(bool(key), "NEXUSMODS_API_KEY is missing")
    request = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"apikey": key, "accept": "application/json", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read()
            response_type = str(response.headers.get("Content-Type", "missing")).replace(key, "[redacted]")
            context = f"HTTP {response.status}; Content-Type={response_type}; fields=unavailable"
            if not body:
                if response.status == 204:
                    return None
                raise RuntimeError(f"error: Nexus {method} {path}: empty response; required=JSON object; {context}")
            try:
                answer = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError) as cause:
                reason = cause.msg if isinstance(cause, json.JSONDecodeError) else cause.reason
                raise RuntimeError(f"error: Nexus {method} {path}: invalid response JSON: {reason}; {context}") from cause
            if not isinstance(answer, dict):
                raise RuntimeError(f"error: Nexus {method} {path}: response is not a JSON object; {context}")
            fields = json.dumps(sorted(answer)).replace(key, "[redacted]")
            context = f"HTTP {response.status}; Content-Type={response_type}; fields={fields}"
            if all(name in answer for name in ("type", "title", "status", "detail", "instance")):
                detail = str(answer["detail"]).replace(key, "[redacted]")[:400]
                raise RuntimeError(f"error: Nexus {method} {path}: API status={answer['status']}; {detail}; {context}")
            flat = path.endswith(("/dependencies/ranges", "/dependencies/dlc"))
            data = answer if flat else answer.get("data")
            if not isinstance(data, dict):
                shape = "errorData response" if "errorData" in answer else "missing or invalid data object"
                raise RuntimeError(f"error: Nexus {method} {path}: {shape}; {context}; inspect Nexus before retry")
            field = ("dependency_definitions" if path.endswith("/dependencies/ranges") else
                     "dlc_dependency_definitions" if path.endswith("/dependencies/dlc") else
                     "mods" if path == "/mods/batch" else
                     "mod_files" if path.endswith("/files") else
                     "versions" if path.endswith("/versions") else None)
            if field and not isinstance(data.get(field), list):
                raise RuntimeError(f"error: Nexus {method} {path}: missing or invalid {field} array; {context}")
            return data
    except urllib.error.HTTPError as cause:
        try:
            problem = json.loads(cause.read())
        except (json.JSONDecodeError, UnicodeDecodeError) as decode:
            reason = decode.msg if isinstance(decode, json.JSONDecodeError) else decode.reason
            raise RuntimeError(f"error: Nexus {method} {path}: HTTP {cause.code}; invalid problem JSON: {reason}") from cause
        detail = problem.get("detail") if isinstance(problem, dict) else None
        reason = (detail if isinstance(detail, str) else str(cause.reason)).replace(key, "[redacted]")[:400]
        raise RuntimeError(f"error: Nexus {method} {path}: HTTP {cause.code}; {reason}; inspect Nexus before retry") from cause
    except urllib.error.URLError as cause:
        raise RuntimeError(f"error: Nexus {method} {path}: {cause.reason}; inspect Nexus before retry") from cause

def check_parent(identity, rows, details, files):
    require(len(rows) == 1, f"Nexus parent lookup returned {len(rows)} rows; required=1")
    parent = rows[0]
    require(str(parent.get("id")) == identity["uid"], "Nexus parent UID differs")
    require(str(parent.get("game_id")) == "10562", "Nexus game differs from The Cabin Game")
    require(parent.get("status") == "not_published", f"Nexus parent status={parent.get('status')}; required=not_published")
    require(str(details.get("id")) == identity["uid"], "Nexus scoped page UID differs")
    require(str(details.get("game_scoped_id")) == identity["scoped"], "Nexus scoped page ID differs")
    require(str(details.get("game_id")) == "10562", "Nexus scoped page game differs")
    matches = [row for row in files if str(row.get("id")) == identity["file"]]
    require(len(matches) == 1, "Nexus file group does not belong to the configured mod")
    return parent

def parent(identity):
    rows = api("POST", "/mods/batch", {"mod_ids": [identity["uid"]]})["mods"]
    details = api("GET", f"/games/thecabingame/mods/{identity['scoped']}")
    files = api("GET", f"/mods/{identity['uid']}/files")["mod_files"]
    return check_parent(identity, rows, details, files)

def ranges(definitions):
    require(bool(definitions), "file-to-file requirements are missing")
    result = []
    for definition in definitions:
        values = []
        for value in definition["ranges"]:
            minimum = value["min_version"]
            maximum = value["max_version"]
            target = value["target_mod_file"]
            require(str(minimum["file"]["id"]) == str(target["id"]), "dependency minimum belongs to another file")
            if maximum:
                require(str(maximum["file"]["id"]) == str(target["id"]), "dependency maximum belongs to another file")
            values.append({"min_version_id": str(minimum["id"]), "max_version_id": str(maximum["id"]) if maximum else None})
        require(bool(values), "dependency definition has no ranges")
        result.append({"ranges": values})
    return {"dependency_definitions": result}

def write_output(values):
    output = os.environ.get("GITHUB_OUTPUT")
    require(bool(output), "GITHUB_OUTPUT is missing")
    with open(output, "a", encoding="utf-8") as stream:
        for name, value in values.items():
            require("\n" not in str(value), f"workflow output contains a newline: {name}")
            stream.write(f"{name}={value}\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["preflight", "verify"])
    args = parser.parse_args()
    identity = {"uid": os.environ.get("NEXUS_MOD_ID", ""), "file": os.environ.get("NEXUS_FILE_GROUP_ID", ""), "scoped": os.environ.get("NEXUS_GAME_SCOPED_ID", "")}
    require(all(value.isdigit() for value in identity.values()), "Nexus IDs are missing or invalid")
    current_parent = parent(identity)
    if args.phase == "preflight":
        config = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        accepted = json.loads((ROOT / "acceptance.json").read_text(encoding="utf-8")).get("accepted") is True
        archive = ROOT / "dist" / f"{config['mod']}-{config['version']}{'' if accepted else '-candidate'}.zip"
        require(archive.is_file(), f"built archive is missing: {archive}")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        version = f"{config['version']}-{'ready' if accepted else 'candidate'}.{digest[:12]}"
        versions = api("GET", f"/mod-files/{identity['file']}/versions")["versions"]
        active = [item for item in versions if item["category"] == "main"]
        require(bool(active), "configured Nexus file has no Main version")
        previous = max(active, key=lambda item: Decimal(item["position"]))
        require(str(previous["file"]["id"]) == identity["file"], "previous version belongs to another file group")
        dependencies = ranges(api("GET", f"/mod-file-versions/{previous['id']}/dependencies/ranges")["dependency_definitions"])
        dlc = api("GET", f"/mod-file-versions/{previous['id']}/dependencies/dlc")["dlc_dependency_definitions"]
        require(not dlc, "unexpected DLC dependencies; draft update requires an explicit supported mapping")
        ready = previous["version"] != version
        receipt = {"identity": identity, "archive": str(archive), "sha256": digest, "version": version, "previous_version_id": previous["id"], "dependencies": dependencies, "status": current_parent["status"], "accepted": accepted, "upload_required": ready}
        RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        write_output({"ready": str(ready).lower(), "asset": archive, "version": version, "display_name": f"{config['mod']} {config['version']}{'' if accepted else ' candidate'}"})
        print(f"info: draft preflight confirmed mod={identity['uid']} file={identity['file']} status=not_published; upload_needed={ready}; sha256={digest}")
    else:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        require(receipt["identity"] == identity, "Nexus identity changed after preflight")
        versions = api("GET", f"/mod-files/{identity['file']}/versions")["versions"]
        uploaded_id = os.environ.get("NEXUS_VERSION_ID")
        require(not receipt["upload_required"] or bool(uploaded_id), "Nexus upload returned no version acknowledgement; inspect Nexus before retry")
        if uploaded_id:
            matches = [row for row in versions if str(row["id"]) == uploaded_id]
        else:
            matches = [row for row in versions if row["version"] == receipt["version"] and row["category"] == "main"]
        require(len(matches) == 1, "uploaded Nexus version is unconfirmed; inspect Nexus before retry")
        version = matches[0]
        require(version["version"] == receipt["version"] and str(version["file"]["id"]) == identity["file"], "uploaded Nexus version/file differs")
        # New file versions need the same range definitions as the replaced version.
        if uploaded_id:
            parent(identity)
            api("PUT", f"/mod-file-versions/{version['id']}/dependencies/ranges", receipt["dependencies"])
        actual = ranges(api("GET", f"/mod-file-versions/{version['id']}/dependencies/ranges")["dependency_definitions"])
        require(actual == receipt["dependencies"], "Nexus file-to-file requirements readback differs")
        parent(identity)
        receipt.update({"confirmed_version_id": version["id"], "requirements_confirmed": True, "parent_unpublished_confirmed": True})
        RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(f"Confirmed unpublished Nexus file {version['id']}, version {receipt['version']}, file-to-file requirements preserved.\nSHA256: {receipt['sha256']}\n")
        print(f"info: Nexus version={version['id']} confirmed; file-to-file requirements read back; parent remains unpublished")

if __name__ == "__main__":
    main()
