"""
Grundschutz++ OSCAL → Flat Tabellen für Power Platform / Dataverse.

Erzeugt drei Tabellen:
1. grundschutz_controls     — eine Zeile pro Control (inkl. Sub-Controls)
2. grundschutz_control_links — Cross-References (related / required)
3. grundschutz_groups        — Baustein-Hierarchie (Lookup)

Alle Tabellen tragen catalog_version + catalog_commit für Versionstracking.
Ein content_hash pro Control ermöglicht Änderungserkennung im Update-Lauf.
"""
import json
import hashlib
import re
import subprocess
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

ROOT = Path("/home/claude/grundschutz/Stand-der-Technik-Bibliothek")
CATALOG_PATH = ROOT / "Anwenderkataloge/Grundschutz++/Grundschutz++-catalog.json"
OUT_DIR = Path("/home/claude/grundschutz/out")
OUT_DIR.mkdir(exist_ok=True)

# ---------- Katalog + Git-Metadaten laden ----------
with CATALOG_PATH.open() as f:
    doc = json.load(f)
cat = doc["catalog"]

def git(args):
    return subprocess.run(["git", "-C", str(ROOT)] + args, capture_output=True, text=True).stdout.strip()

CATALOG_COMMIT_FULL = git(["log", "-1", "--format=%H", "--",
                           "Anwenderkataloge/Grundschutz++/Grundschutz++-catalog.json"])
CATALOG_COMMIT_SHORT = CATALOG_COMMIT_FULL[:7]
CATALOG_COMMIT_DATE = git(["log", "-1", "--format=%aI", "--",
                           "Anwenderkataloge/Grundschutz++/Grundschutz++-catalog.json"])
CATALOG_VERSION = cat["metadata"].get("version", "")
CATALOG_LAST_MODIFIED = cat["metadata"].get("last-modified", "")
SOURCE_URL = (
    "https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek/blob/"
    f"{CATALOG_COMMIT_FULL}/Anwenderkataloge/Grundschutz++/Grundschutz++-catalog.json"
)

print(f"Katalog-Version: {CATALOG_VERSION}")
print(f"Git-Commit:      {CATALOG_COMMIT_FULL} ({CATALOG_COMMIT_DATE})")

# ---------- Hilfsfunktionen ----------
def props_dict(item):
    """Liste von OSCAL-Props → dict (Name → Wert). Bei Duplikaten wird der erste Wert als Primärwert, alle als Liste gespeichert."""
    d = {}
    for p in item.get("props", []):
        name = p["name"]
        val = p["value"]
        if name in d:
            if not isinstance(d[name], list):
                d[name] = [d[name]]
            d[name].append(val)
        else:
            d[name] = val
    return d

def params_dict(control):
    """Params (für Template-Substitution): id → erster value."""
    d = {}
    for p in control.get("params", []):
        vals = p.get("values") or []
        d[p["id"]] = vals[0] if vals else (p.get("label") or "")
    return d

PARAM_RE = re.compile(r"\{\{\s*insert:\s*param,\s*([^\s}]+)\s*\}\}")
CURLY_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")

def resolve_prose(prose, params):
    """`{{ insert: param, xyz }}` → Parameterwert. `{{ freier Text }}` → `freier Text`."""
    if not prose:
        return ""
    out = PARAM_RE.sub(lambda m: params.get(m.group(1), f"[param:{m.group(1)}]"), prose)
    out = CURLY_RE.sub(lambda m: m.group(1).strip(), out)
    return out

def hash_content(control):
    """Stabiler Hash über relevante Felder → Änderungserkennung."""
    sig = {
        "title": control.get("title"),
        "class": control.get("class"),
        "props": sorted((p["name"], p["value"]) for p in control.get("props", [])),
        "params": sorted(
            (p["id"], tuple(p.get("values") or []))
            for p in control.get("params", [])
        ),
        "parts": sorted(
            (part.get("name"), part.get("prose", ""),
             tuple(sorted((p["name"], p["value"]) for p in part.get("props", []))))
            for part in control.get("parts", [])
        ),
        "links": sorted((l.get("href"), l.get("rel")) for l in control.get("links", [])),
        "sub_control_ids": sorted(sc["id"] for sc in control.get("controls", [])),
    }
    blob = json.dumps(sig, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

# ---------- Flache Strukturen aufbauen ----------
rows_controls = []
rows_links = []
rows_groups = []

def process_control(ctrl, parent_id, group_l1, group_l2, level):
    props = props_dict(ctrl)
    params = params_dict(ctrl)

    # Parts extrahieren
    statement_part = next((p for p in ctrl.get("parts", []) if p.get("name") == "statement"), None)
    guidance_part  = next((p for p in ctrl.get("parts", []) if p.get("name") == "guidance"),  None)

    statement_raw = (statement_part or {}).get("prose", "")
    statement_resolved = resolve_prose(statement_raw, params)
    guidance_raw = (guidance_part or {}).get("prose", "")
    guidance_resolved = resolve_prose(guidance_raw, params)

    stmt_props = props_dict(statement_part) if statement_part else {}

    # Tags: können Liste sein
    tags = props.get("tags")
    if isinstance(tags, list):
        tags_str = "; ".join(tags)
    else:
        tags_str = tags or ""

    sub_controls = ctrl.get("controls", [])
    has_children = len(sub_controls) > 0

    row = {
        "control_id":              ctrl["id"],
        "parent_control_id":       parent_id or "",
        "level":                   level,
        "is_parent":               has_children,
        "title":                   ctrl.get("title", ""),
        "class":                   ctrl.get("class", ""),
        "alt_identifier":          props.get("alt-identifier", ""),
        "group_id_l1":             group_l1["id"],
        "group_title_l1":          group_l1["title"],
        "group_id_l2":             group_l2["id"],
        "group_title_l2":          group_l2["title"],
        "sec_level":               props.get("sec_level", ""),
        "effort_level":            props.get("effort_level", ""),
        "tags":                    tags_str,
        "modal_verb":              stmt_props.get("modal_verb", ""),
        "action_word":             stmt_props.get("action_word", ""),
        "result":                  stmt_props.get("result", ""),
        "result_specification":    stmt_props.get("result_specification", ""),
        "documentation_guideline": stmt_props.get("documentation", ""),
        "statement_resolved":      statement_resolved,
        "statement_raw":           statement_raw,
        "guidance_resolved":       guidance_resolved,
        "catalog_version":         CATALOG_VERSION,
        "catalog_last_modified":   CATALOG_LAST_MODIFIED,
        "catalog_commit":          CATALOG_COMMIT_FULL,
        "catalog_commit_short":    CATALOG_COMMIT_SHORT,
        "catalog_commit_date":     CATALOG_COMMIT_DATE,
        "source_url":              SOURCE_URL,
        "content_hash":            hash_content(ctrl),
    }
    rows_controls.append(row)

    # Links (Cross-References)
    for link in ctrl.get("links", []):
        href = link.get("href", "")
        target = href[1:] if href.startswith("#") else href
        rows_links.append({
            "from_control_id":  ctrl["id"],
            "to_control_id":    target,
            "rel":              link.get("rel", ""),
            "catalog_commit":   CATALOG_COMMIT_FULL,
        })

    # Rekursion in Sub-Controls
    for sub in sub_controls:
        process_control(sub, ctrl["id"], group_l1, group_l2, level + 1)

# Gruppen durchlaufen
for g1 in cat["groups"]:
    group_l1 = {"id": g1["id"], "title": g1["title"]}
    rows_groups.append({
        "group_id":           g1["id"],
        "parent_group_id":    "",
        "level":              1,
        "title":              g1["title"],
        "catalog_commit":     CATALOG_COMMIT_FULL,
    })
    for g2 in g1.get("groups", []):
        group_l2 = {"id": g2["id"], "title": g2["title"]}
        rows_groups.append({
            "group_id":           g2["id"],
            "parent_group_id":    g1["id"],
            "level":              2,
            "title":              g2["title"],
            "catalog_commit":     CATALOG_COMMIT_FULL,
        })
        for ctrl in g2.get("controls", []):
            process_control(ctrl, parent_id=None, group_l1=group_l1, group_l2=group_l2, level=1)

print(f"Controls:        {len(rows_controls)}")
print(f"Cross-Refs:      {len(rows_links)}")
print(f"Gruppen:         {len(rows_groups)}")

# ---------- Nach XLSX schreiben ----------
def write_xlsx(path, rows, title, freeze="A2"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    if not rows:
        wb.save(path); return
    cols = list(rows[0].keys())
    # Header
    header_fill = PatternFill("solid", fgColor="1F3864")
    header_font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    for j, c in enumerate(cols, 1):
        cell = ws.cell(row=1, column=j, value=c)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True)
    ws.row_dimensions[1].height = 28

    for i, row in enumerate(rows, 2):
        for j, c in enumerate(cols, 1):
            ws.cell(row=i, column=j, value=row.get(c, ""))

    # Spaltenbreiten
    widths = {
        "control_id": 14, "parent_control_id": 16, "level": 7, "is_parent": 10,
        "title": 45, "class": 32, "alt_identifier": 38,
        "group_id_l1": 10, "group_title_l1": 28, "group_id_l2": 10, "group_title_l2": 28,
        "sec_level": 12, "effort_level": 10, "tags": 22,
        "modal_verb": 12, "action_word": 14, "result": 50, "result_specification": 45,
        "documentation_guideline": 28, "statement_resolved": 80, "statement_raw": 80,
        "guidance_resolved": 80,
        "catalog_version": 32, "catalog_last_modified": 32, "catalog_commit": 44,
        "catalog_commit_short": 12, "catalog_commit_date": 26, "source_url": 60, "content_hash": 20,
        "from_control_id": 16, "to_control_id": 16, "rel": 12,
        "group_id": 12, "parent_group_id": 16,
    }
    for j, c in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(j)].width = widths.get(c, 20)

    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)
    print(f"→ {path.name}")

write_xlsx(OUT_DIR / "grundschutz_controls.xlsx", rows_controls, "Controls")
write_xlsx(OUT_DIR / "grundschutz_control_links.xlsx", rows_links, "Links")
write_xlsx(OUT_DIR / "grundschutz_groups.xlsx", rows_groups, "Groups")

# ---------- CSV-Export für maschinelle Pipelines ----------
import csv
for name, rows in [
    ("grundschutz_controls", rows_controls),
    ("grundschutz_control_links", rows_links),
    ("grundschutz_groups", rows_groups),
]:
    if not rows: continue
    with (OUT_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"→ {name}.csv")

# ---------- Distribution-Payload (das ist DIE Datei, die Kunden hochladen) ----------
# Ein einziges JSON → hnlz_Katalogstaende.hnlz_payload
payload = {
    "schema_version": "1.0",
    "paket": {
        "kennung": "BSI Grundschutz++",
        "beschreibung": "Anwenderkatalog Grundschutz++ (BSI Stand der Technik)",
    },
    "source": {
        "repository": "BSI-Bund/Stand-der-Technik-Bibliothek",
        "path": "Anwenderkataloge/Grundschutz++/Grundschutz++-catalog.json",
        "commit": CATALOG_COMMIT_FULL,
        "commit_short": CATALOG_COMMIT_SHORT,
        "commit_date": CATALOG_COMMIT_DATE,
        "url": SOURCE_URL,
    },
    "catalog": {
        "version": CATALOG_VERSION,
        "last_modified": CATALOG_LAST_MODIFIED,
    },
    "counts": {
        "controls": len(rows_controls),
        "links": len(rows_links),
        "groups": len(rows_groups),
    },
    "controls": rows_controls,
    "links":    rows_links,
    "groups":   rows_groups,
}
payload_path = OUT_DIR / "grundschutz-pp-flat.json"
with payload_path.open("w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
print(f"→ {payload_path.name}  ({payload_path.stat().st_size / 1024:.0f} KB)")

# ---------- Manifest (klein, für GitHub Release Body + Flow-Validierung) ----------
manifest = {
    "schema_version": "1.0",
    "paket": payload["paket"],
    "source": payload["source"],
    "catalog": payload["catalog"],
    "counts": payload["counts"],
    "counts_by_class": {},
    "counts_by_sec_level": {},
    "payload_sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(),
    "payload_bytes": payload_path.stat().st_size,
    "release_tag": f"grundschutz-pp-{CATALOG_COMMIT_SHORT}",
}
from collections import Counter
manifest["counts_by_class"] = dict(Counter(r["class"] for r in rows_controls))
manifest["counts_by_sec_level"] = dict(Counter(r["sec_level"] for r in rows_controls))

with (OUT_DIR / "manifest.json").open("w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print(f"→ manifest.json")
print()
print("=== Distribution-Artefakte fertig ===")
for p in sorted(OUT_DIR.iterdir()):
    print(f"  {p.name:40s} {p.stat().st_size:>10,} bytes")
