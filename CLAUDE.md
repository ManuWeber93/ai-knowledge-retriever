# Claude-Anweisungen für dieses Projekt

## Dokumentation aktuell halten

Nach **jeder Änderung** am Projekt — egal ob Code, Konfiguration oder Schema —
müssen die folgenden Dateien geprüft und bei Bedarf aktualisiert werden:

| Datei | Inhalt | Aktualisieren wenn … |
|---|---|---|
| `README.md` | Setup-Anleitung, Voraussetzungen, Projektstruktur | sich Abhängigkeiten, Befehle, Env-Variablen oder die Dateistruktur ändern |
| `docs/architecture.md` | Übergeordnete Architektur, Komponentendiagramm, Datenmodell, Technologie-Entscheidungen | sich Komponenten, Schnittstellen, das DB-Schema oder Technologieentscheide ändern |
| `docs/INTERNALS.md` | Konkreter Code-Ablauf, Komponenten-Zusammenspiel | sich Logik, Funktionsnamen, Datenfluss oder das Zusammenspiel der Module ändert |

Die Dokumentation wird **im selben Schritt** wie die Code-Änderung aktualisiert —
nicht nachträglich als separater Schritt.

## Sprache

- Code, Variablennamen, Kommentare: **Englisch**
- Dokumentation (`README.md`, `docs/`): **Deutsch**

## Code-Qualität

- Variablennamen sind vollständig ausgeschrieben (keine Abkürzungen wie `cls`, `ext_id`, `ln`)
- Keine Ausrichtungs-Leerzeichen bei Zuweisungen (PEP 8)
- Kommentare nur wenn das **Warum** nicht offensichtlich ist — nie das **Was**
