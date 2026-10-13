"""Announce published releases and verify the destination and saved Discord message."""
import json
import hashlib
import zlib
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_notes
import urllib.error
import urllib.parse
import urllib.request

def request_json(url, label, headers=None, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{label}: HTTP{error.code} {error.reason}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        reason = str(getattr(error, "reason", error))
        reason = re.sub(r"https://[^\s'\"]+", "[URL redacted]", reason)
        raise RuntimeError(f"{label}: {reason}; delivery is unconfirmed") from error

def build_payload(release, name, description, support, thumbnail, nexus, repository):
    if release["draft"] or not release.get("published_at"):
        raise ValueError("release is not published")
    if urllib.parse.urlparse(thumbnail).scheme != "https":
        raise ValueError("product thumbnail requires an HTTPS image URL")
    if not re.fullmatch(r"https://www\.nexusmods\.com/thecabingame/mods/[1-9][0-9]*", nexus):
        raise ValueError("Nexus link requires a canonical The Cabin Game product URL")
    title = name + " " + release["tag_name"].removeprefix("v")
    if release["prerelease"]:
        title += " (pre-release)"
    description = release_notes.section(release["tag_name"].removeprefix("v"))
    if len(description) > 1400:
        description = description[:1400] + "\n..."
    links = f"[Nexus]({nexus}) · [GitHub]({release['html_url']})"
    short = repository.rsplit("/", 1)[-1]
    return {"allowed_mentions": {"parse": []}, "embeds": [{
        "title": title, "url": release["html_url"], "description": description,
        "color": 8256434, "thumbnail": {"url": thumbnail},
        "fields": [{"name": "Get it", "value": links}],
        "footer": {"text": "The Cabin Game · " + short},
    }]}

def announce(webhook, expected_channel, payload, send, record):
    parsed = urllib.parse.urlparse(webhook)
    if parsed.scheme != "https" or parsed.hostname not in {"discord.com", "discordapp.com"} or not re.fullmatch(r"/api(?:/v[0-9]+)?/webhooks/[0-9]+/[A-Za-z0-9._-]+(?:/github)?", parsed.path):
        raise ValueError("invalid Discord webhook address")
    webhook = urllib.parse.urlunparse(parsed._replace(path=parsed.path.removesuffix("/github"), query="", fragment=""))
    headers = {"User-Agent": "DooDesch-Release-Announcement", "Content-Type": "application/json"}
    target = request_json(webhook, "read Discord destination", headers)
    if target.get("channel_id") != expected_channel:
        raise ValueError(f"Discord destination mismatch: measured {target.get('channel_id')}, required {expected_channel}")
    record.update(channel_id=expected_channel, status="checked", payload=payload)
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if not send:
        print(f"info: Discord channel {expected_channel} confirmed; announcement deliberately not sent")
        return record
    record["status"] = "attempted"
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"info: sending release announcement to Discord channel {expected_channel}")
    message = request_json(webhook + "?wait=true", "send Discord announcement", headers, payload)
    message_id = message.get("id", "")
    if not message_id or message.get("channel_id") != expected_channel:
        raise ValueError("Discord returned no matching message acknowledgement; inspect the channel before retry")
    record.update(status="acknowledged", message_id=message_id)
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"info: Discord acknowledged message {message_id}")
    saved = request_json(webhook + "/messages/" + message_id, "read saved Discord announcement", headers)
    if saved.get("id") != message_id or saved.get("channel_id") != expected_channel:
        raise ValueError("saved Discord message does not match its acknowledgement")
    record.update(status="confirmed", message_url=f"https://discord.com/channels/{target['guild_id']}/{expected_channel}/{message_id}")
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"confirmed: Discord message {message_id} is saved in channel {expected_channel}")
    return record

PRODUCT = {'repository': 'DooDesch-Mods/TheCabinGame-ShortEvents', 'name': 'Cabin Short Events', 'summary': 'Reduces balloon and train task goals by about one third.', 'support': 'https://support.doodesch.de/shortevents', 'thumbnail': 'https://raw.githubusercontent.com/DooDesch-Mods/TheCabinGame-ShortEvents/main/docs/thumbnail.png'}

CHANNEL = "1534536549642014810"

def check_product():
    if os.environ.get("GITHUB_REPOSITORY") != PRODUCT["repository"]:
        raise ValueError("release repository differs from this product")
    if os.environ.get("DISCORD_CHANNEL_ID") != CHANNEL:
        raise ValueError("release channel differs from pinned github channel")
    for name in ("NAME", "SUMMARY", "SUPPORT", "THUMBNAIL"):
        if os.environ.get("PRODUCT_" + name) != PRODUCT[name.lower()]:
            raise ValueError("release product mapping differs: " + name)


def check_thumbnail(path=None):
    path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "docs/thumbnail.png"
    if not path.is_file():
        raise ValueError("actual product PNG is missing: docs/thumbnail.png; announcement not sent")
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("product thumbnail is not PNG")
    offset = 8
    chunks = []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("product PNG is truncated")
        length = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data) or zlib.crc32(data[offset + 4:end - 4]) != int.from_bytes(data[end - 4:end], "big"):
            raise ValueError("product PNG chunk is truncated or has invalid CRC")
        chunks.append(kind)
        if kind == b"IHDR":
            if length != 13 or not int.from_bytes(data[offset + 8:offset + 12], "big") or not int.from_bytes(data[offset + 12:offset + 16], "big"):
                raise ValueError("product PNG dimensions are invalid")
        offset = end
        if kind == b"IEND":
            break
    if not chunks or chunks[0] != b"IHDR" or b"IDAT" not in chunks or chunks[-1] != b"IEND" or offset != len(data):
        raise ValueError("product PNG structure is incomplete")
    return hashlib.sha256(data).hexdigest()


def check_prior_attempt():
    path = Path("discord-result.json")
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("status") in {"attempted", "acknowledged", "confirmed"}:
            raise ValueError("prior Discord send attempt retained; inspect saved message before retry")


def run():
    tag = os.environ.get("RELEASE_TAG", "")
    send = os.environ.get("SEND_ANNOUNCEMENT") == "true"
    if send and not tag:
        raise ValueError("sending requires a published release tag")
    check_product()
    if send:
        check_prior_attempt()
    repo = os.environ["GITHUB_REPOSITORY"]
    record = {"release_tag": tag or None, "repository": repo}
    payload = {}
    if tag:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", tag):
            raise ValueError(f"invalid release tag: {tag!r}")
        release = request_json(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", "read published GitHub release", {"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json"})
        if release["tag_name"] != tag:
            raise ValueError("GitHub release tag differs from requested tag")
        if send and release.get("prerelease"):
            raise ValueError("automatic announcement requires a published full release")
        if send:
            record["thumbnail_sha256"] = check_thumbnail()
        record["release_id"] = release["id"]
        payload = build_payload(release, os.environ["PRODUCT_NAME"], os.environ["PRODUCT_SUMMARY"], os.environ["PRODUCT_SUPPORT"], os.environ["PRODUCT_THUMBNAIL"], os.environ.get("NEXUS_MOD_URL", ""), repo)
    webhook = os.environ.get("DISCORD_RELEASE_WEBHOOK", "")
    if not webhook:
        raise ValueError("DISCORD_RELEASE_WEBHOOK is missing; release announcement cannot run")
    result = announce(webhook, os.environ["DISCORD_CHANNEL_ID"], payload, send, record)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"Discord: {result['status']}. Channel: {result['channel_id']}.\n\n" + result.get("message_url", "No message sent.") + "\n")

if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        raise SystemExit(f"error: release announcement failed: {error}") from None
