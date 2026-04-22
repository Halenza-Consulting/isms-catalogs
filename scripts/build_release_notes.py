"""
Erzeugt CHANGELOG.md für ein Katalog-Release, indem das aktuelle Payload
(grundschutz-pp-flat.json) mit dem Payload des vorherigen GitHub-Releases
verglichen wird. Match-Key: alt_identifier (stabile UUID aus OSCAL).
Änderungserkennung: content_hash.

Aufruf:
  python build_release_notes.py CURRENT.json PREVIOUS.json OUTPUT.md

Wenn PREVIOUS.json nicht existiert (erstes Release), wird ein Initial-
Changelog ohne Diff erzeugt.
"""
import json
import sys
from pathlib import Path
from collections import Counter

current_path = Path(sys.argv[1])
previous_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("CHANGELOG.md")

current = json.loads(current_path.read_text(encoding="utf-8"))
curr_controls = {c["alt_identifier"]: c for c in current["controls"] if c.get("alt_identifier")}

previous = None
if previous_path and previous_path.exists() and previous_path.stat().st_size > 0:
    previous = json.loads(previous_path.read_text(encoding="utf-8"))

lines = []
src = current["source"]
cat = current["catalog"]
paket = current["paket"]
counts = current["counts"]

lines.append(f"# {paket['kennung']} — Release `{current['source']['commit_short']}`")
lines.append("")
lines.append(f"**BSI-Katalog-Version:** `{cat['version']}`  ")
lines.append(f"**BSI-Commit:** [`{src['commit_short']}`]({src['url']}) vom {src['commit_date'][:10]}  ")
lines.append(f"**Controls gesamt:** {counts['controls']}")
lines.append("")

if previous is None:
    lines.append("## Erste Veröffentlichung")
    lines.append("")
    lines.append("Dies ist die initiale Distribution des Katalogs. Kein Diff verfügbar.")
    lines.append("")
    lines.append("| Kategorie | Anzahl |")
    lines.append("|---|---|")
    by_class = Counter(c["class"] for c in current["controls"])
    for cls, n in by_class.most_common():
        lines.append(f"| Klasse `{cls}` | {n} |")
    by_sec = Counter(c["sec_level"] for c in current["controls"])
    for sec, n in by_sec.most_common():
        lines.append(f"| Schutzniveau `{sec}` | {n} |")
else:
    prev_controls = {c["alt_identifier"]: c for c in previous["controls"] if c.get("alt_identifier")}
    curr_keys = set(curr_controls.keys())
    prev_keys = set(prev_controls.keys())

    added = sorted(curr_keys - prev_keys)
    removed = sorted(prev_keys - curr_keys)
    common = curr_keys & prev_keys
    changed = sorted(
        k for k in common
        if curr_controls[k]["content_hash"] != prev_controls[k]["content_hash"]
    )
    unchanged = len(common) - len(changed)

    lines.append(f"## Änderungen gegenüber `{previous['source']['commit_short']}`")
    lines.append("")
    lines.append(f"- **Neu:** {len(added)}")
    lines.append(f"- **Geändert:** {len(changed)}")
    lines.append(f"- **Entfernt:** {len(removed)}")
    lines.append(f"- **Unverändert:** {unchanged}")
    lines.append("")

    def _row(c):
        return f"| `{c.get('control_id','?')}` | {c.get('title','')[:80]} | `{c.get('alt_identifier','')[:8]}…` |"

    if added:
        lines.append("### Neue Controls")
        lines.append("")
        lines.append("| Control-ID | Titel | alt_identifier |")
        lines.append("|---|---|---|")
        for k in added:
            lines.append(_row(curr_controls[k]))
        lines.append("")

    if changed:
        lines.append("### Geänderte Controls")
        lines.append("")
        lines.append("| Control-ID | Titel | alt_identifier |")
        lines.append("|---|---|---|")
        for k in changed:
            lines.append(_row(curr_controls[k]))
        lines.append("")
        lines.append("**Hinweis:** Diese Controls tragen beim Import das Review-Flag. Bestehende")
        lines.append("Feststellungen werden nicht überschrieben, sondern bleiben zur manuellen Prüfung stehen.")
        lines.append("")

    if removed:
        lines.append("### Entfernte Controls")
        lines.append("")
        lines.append("| Control-ID (alt) | Titel | alt_identifier |")
        lines.append("|---|---|---|")
        for k in removed:
            lines.append(_row(prev_controls[k]))
        lines.append("")
        lines.append("**Hinweis:** Entfernte Controls werden beim Import deaktiviert, nicht gelöscht,")
        lines.append("damit Historie und Feststellungen erhalten bleiben.")
        lines.append("")

lines.append("## Import")
lines.append("")
lines.append("1. In der ISMS-App: **Katalog-Verwaltung → Neuer Katalogstand**")
lines.append("2. `grundschutz-pp-flat.json` aus diesem Release hochladen")
lines.append("3. **Verarbeiten** klicken — der Flow übernimmt Upsert mit alt_identifier-Matching")
lines.append("")

output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"→ {output_path}")
