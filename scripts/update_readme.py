"""Refresh the auto-generated sections of this profile README.

Reads ROADMAP.md, CERTS.md and LOG.md from the owner's public cloud-journey repo,
and lists every public repo the owner has tagged with the topic `portfolio`.
Standard library only, so it runs on any GitHub Actions runner with no installs.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

LOGIN = os.environ["GH_LOGIN"]
TOKEN = os.environ.get("GITHUB_TOKEN", "")
JOURNEY = os.environ.get("JOURNEY_REPO", "cloud-journey")
README = os.environ.get("README_PATH", "README.md")
API = "https://api.github.com"


def fetch(url, api=True):
    headers = {"User-Agent": f"{LOGIN}-profile-updater"}
    if api:
        headers["Accept"] = "application/vnd.github+json"
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def journey_file(path):
    url = f"https://raw.githubusercontent.com/{LOGIN}/{JOURNEY}/HEAD/{path}"
    try:
        return fetch(url, api=False)
    except urllib.error.URLError as err:
        print(f"warning: could not read {path}: {err}", file=sys.stderr)
        return ""


CHECK = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")


def parse_phases(md):
    phases = []
    for line in md.splitlines():
        heading = re.match(r"^##\s+(Phase\b.*)$", line)
        if heading:
            phases.append({"name": heading.group(1).strip(), "done": 0, "total": 0})
            continue
        box = CHECK.match(line)
        if box and phases:
            phases[-1]["total"] += 1
            phases[-1]["done"] += box.group(1).lower() == "x"
    return phases


def bar(done, total, width=10):
    if total == 0:
        return "░" * width + "   0%"
    filled = round(width * done / total)
    pct = round(100 * done / total)
    return "▓" * filled + "░" * (width - filled) + f" {pct:3d}%"


def render_progress(phases):
    if not phases:
        return "_Roadmap not found._"
    rows = ["| Phase | Progress |", "| --- | --- |"]
    for p in phases:
        status = "Done" if p["total"] and p["done"] == p["total"] else bar(p["done"], p["total"])
        rows.append(f"| {p['name']} | `{status}` |")
    return "\n".join(rows)


def render_focus(phases):
    current = next((p for p in phases if p["done"] < p["total"]), None)
    if current is None:
        return "**Current focus:** Sharpening: new projects and certifications"
    return f"**Current focus:** {current['name']}"


def render_certs(md):
    rows = ["| Certification | Status |", "| --- | --- |"]
    found = False
    for line in md.splitlines():
        box = CHECK.match(line)
        if not box:
            continue
        found = True
        text = box.group(2).strip()
        name, _, note = text.partition(" - ")
        status = "Earned" if box.group(1).lower() == "x" else (note.strip() or "Planned")
        rows.append(f"| {name.strip()} | {status} |")
    return "\n".join(rows) if found else "_No certifications listed yet._"


def render_log(md, max_lines=14):
    lines = md.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## ")), None)
    if start is None:
        return "_No log entries yet._"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    entry = [l for l in lines[start:end] if l.strip() and not l.strip().startswith("<!--")]
    title = entry[0][3:].strip()
    body = entry[1:max_lines]
    more = f"\n\n[Read the full log](https://github.com/{LOGIN}/{JOURNEY}/blob/main/LOG.md)"
    return f"**{title}**\n\n" + "\n".join(body) + more


def render_projects():
    query = urllib.parse.quote(f"user:{LOGIN} topic:portfolio")
    try:
        data = json.loads(fetch(f"{API}/search/repositories?q={query}&sort=updated&per_page=20"))
    except urllib.error.URLError as err:
        print(f"warning: project search failed: {err}", file=sys.stderr)
        return None
    items = data.get("items", [])
    if not items:
        return "_First project lands in Phase 4: the Cloud Resume Challenge on Azure._"
    rows = ["| Project | What it is | Stack | Live |", "| --- | --- | --- | --- |"]
    for r in items:
        stack = ", ".join(t for t in r.get("topics", []) if t != "portfolio")[:80] or (r.get("language") or "")
        live = f"[demo]({r['homepage']})" if r.get("homepage") else ""
        desc = (r.get("description") or "").replace("|", "/")
        rows.append(f"| [{r['name']}]({r['html_url']}) | {desc} | {stack} | {live} |")
    return "\n".join(rows)


def replace_section(text, key, content):
    pattern = re.compile(rf"(<!-- AUTO:{key}:start -->\n).*?(\n<!-- AUTO:{key}:end -->)", re.S)
    if not pattern.search(text):
        print(f"warning: markers for {key} not found", file=sys.stderr)
        return text
    return pattern.sub(lambda m: m.group(1) + content + m.group(2), text)


def main():
    with open(README, encoding="utf-8") as f:
        text = f.read()
    roadmap = journey_file("ROADMAP.md")
    phases = parse_phases(roadmap)
    if phases:
        text = replace_section(text, "focus", render_focus(phases))
        text = replace_section(text, "progress", render_progress(phases))
    certs = journey_file("CERTS.md")
    if certs:
        text = replace_section(text, "certs", render_certs(certs))
    log = journey_file("LOG.md")
    if log:
        text = replace_section(text, "log", render_log(log))
    projects = render_projects()
    if projects is not None:
        text = replace_section(text, "projects", projects)
    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("README refreshed")


if __name__ == "__main__":
    main()
