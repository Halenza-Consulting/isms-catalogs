# halenza-consulting/isms-catalogs

Distributions-Repo für kuratierte Compliance-Kataloge, aufbereitet für die Halenza ISMS Power App.

## Was hier passiert

Eine GitHub Action prüft täglich den BSI-Upstream auf Änderungen am Grundschutz++-OSCAL-Katalog. Wenn sich der Commit geändert hat, läuft der Flattener und erzeugt ein neues GitHub Release mit:

**Generische Artefakte** (für Power-Automate-Flows und manuelle Prüfung):

- `grundschutz-pp-flat.json` — komplette Flat-Struktur mit allen Feldern, inklusive Roh-Statements, Guidance und Metadaten. Für Upload in `hnlz_Katalogstaende` und Verarbeitung durch den Upsert-Flow.
- `manifest.json` — kleines Metadaten-File (Commit, Version, Counts, SHA-256 des Payloads). Zur Schnellvalidierung, bevor ein Payload importiert wird.
- `grundschutz_controls.csv` / `.xlsx` — tabellarischer Export aller Controls zur Durchsicht.
- `grundschutz_control_links.csv` — Cross-References zwischen Controls (`related` / `required`).
- `grundschutz_groups.csv` — Baustein-Hierarchie.
- `CHANGELOG.md` — Release Notes mit Diff gegen Vorgänger-Release (neu / geändert / entfernt).

**Dataverse-Import-Artefakte** (für `pac data import` beim Erstimport in eine Kundenumgebung):

- `dataverse-import/crdbf_compgrundschutzextras.csv` — eine Zeile pro Control, Spaltennamen = logische Dataverse-Feldnamen, Picklist-Werte als numerische Option-IDs, IDs als deterministische UUID v5.
- `dataverse-import/crdbf_compliance.csv` — eine Zeile pro Control in der Haupttabelle, mit Paket-Lookup und Extras-Lookup bereits als GUIDs gesetzt.

Alle GUIDs (Extras, Compliance, Paket) sind deterministisch aus dem OSCAL-`alt_identifier` bzw. dem Paket-Namen abgeleitet. Derselbe Katalog-Input erzeugt also in jeder Umgebung dieselben GUIDs. Das macht den Erstimport idempotent und erlaubt später einfache Upserts ohne Lookup-Auflösung zur Laufzeit.

## Upstream-Quelle

- Repo: [`BSI-Bund/Stand-der-Technik-Bibliothek`](https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek)
- Datei: `Anwenderkataloge/Grundschutz++/Grundschutz++-catalog.json`
- Format: [OSCAL 1.1.3](https://pages.nist.gov/OSCAL/) Catalog Model

## Architektur

```
┌─────────────────────┐
│  BSI GitHub Repo    │  (Upstream, OSCAL JSON)
└──────────┬──────────┘
           │  täglich sparse clone
           ▼
┌─────────────────────────────────────────┐
│  halenza-consulting/isms-catalogs       │
│  ┌───────────────────────────────────┐  │
│  │  flatten_grundschutz.py           │  │
│  │  build_release_notes.py           │  │
│  └──────────────┬────────────────────┘  │
│                 ▼                        │
│  GitHub Release: grundschutz-pp-<sha>   │
│    • grundschutz-pp-flat.json           │
│    • manifest.json                      │
│    • generic CSV / XLSX                 │
│    • dataverse-import/*.csv             │
│    • CHANGELOG.md                       │
└──────────┬──────────────────────────────┘
           │  manueller Download durch Admin
           ▼
┌─────────────────────────────────────────┐
│  Kunden-Tenant: ISMS Power App          │
│                                         │
│  Erstimport (pac data import):          │
│    dataverse-import/*.csv               │
│                                         │
│  Folge-Updates (Upsert-Flow):           │
│    hnlz_Katalogstaende-Upload           │
│    → Flow matched via alt_identifier    │
│    → content_hash erkennt Änderungen    │
└─────────────────────────────────────────┘
```

## Aufruf lokal (zum Testen)

```
# BSI-Katalog klonen
git clone --depth=1 --filter=blob:none --sparse \
  https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek.git bsi-upstream
git -C bsi-upstream sparse-checkout set "Anwenderkataloge/Grundschutz++"

# Flattener ausführen
pip install openpyxl
python scripts/flatten_grundschutz.py \
  --catalog   bsi-upstream/Anwenderkataloge/Grundschutz++/Grundschutz++-catalog.json \
  --output-dir out \
  --repo-root bsi-upstream
```

## Release manuell erzwingen

```
gh workflow run sync-grundschutz.yml -f force_release=true
```

Sinnvoll, wenn der Flattener-Code angepasst wurde und ein neuer Release mit demselben Upstream-Commit nötig ist.
