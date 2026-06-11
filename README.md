# AI Knowledge Retriever

Ein selbst gehostetes RAG-System (Retrieval-Augmented Generation), das Wissensdatenbanken
durchsuchbar macht und die Ergebnisse via [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
an einen LLM-Chat weitergibt.

**Wie es funktioniert:** Dokumente werden in Textabschnitte (Chunks) aufgeteilt, in Vektoren
umgewandelt und in PostgreSQL gespeichert. Stellt ein Nutzer eine Frage, werden semantisch
ähnliche Chunks gefunden und als Kontext an ein LLM übergeben — das LLM antwortet auf Basis
der eigenen Wissensdaten.

Eine detaillierte Beschreibung der Codebasis steht in [`INTERNALS.md`](INTERNALS.md),
die übergeordnete Architektur in [`architecture.md`](architecture.md).

---

## Komponenten

| Komponente | Laufzeit | Beschreibung |
|---|---|---|
| **PostgreSQL + pgvector** | Docker | Speichert Dokumente, Chunks und Embeddings |
| **MCP-Server** | Docker | Stellt pro Datenquelle ein Suchtool bereit |
| **mcpo** | Docker | Übersetzt MCP → OpenAPI für Open WebUI |
| **Ingestion** | Host (manuell) | Liest Quellen, chunked, embeddet, schreibt in DB |
| **Ollama** | Host (lokal) | Erzeugt Embeddings (`nomic-embed-text`, 768 dim) |
| **Open WebUI** | Host (lokal) | Chat-Interface, bindet MCP-Server ein |
| **LLM** | Cloud oder lokal | LLM-Modell, entweder Cloud oder lokal |

---

## Voraussetzungen

Folgende Software muss auf dem Host installiert sein:

- **Docker** (mit Docker Compose) — für PostgreSQL und den MCP-Server
- **Ollama** — für Embeddings lokal auf dem Host
  - Nach der Installation: `ollama pull nomic-embed-text`
- **Open WebUI** — als Chat-Interface
- **Python 3.12+** — für die Ingestion-Skripte
- **uv** — Python-Paketmanager für die Ingestion

  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Windows
  winget install astral-sh.uv
  ```

- Lokales LLM oder API-Key für Cloud-LLM

---

## Einmalige Einrichtung

### 1. Repository klonen

```bash
git clone <repo-url>
cd ai-knowledge-retriever
```

### 2. Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
```

### 3. Datenquellen konfigurieren

```bash
cp sources.yaml.example sources.yaml
```

`sources.yaml` öffnen und die gewünschten Quellen eintragen. Die Datei ist in `.gitignore`
aufgenommen, da sie vertrauliche Angaben enthalten kann (interne URLs, Zugangsdaten in `config`).
`sources.yaml.example` dient als versioniertes Template ohne sensible Werte.

> Für das Beispiel-Setup (Wikipedia-Artikel) kann die Datei unverändert verwendet werden.

`.env` öffnen und ausfüllen:

| Variable | Beschreibung |
|---|---|
| `POSTGRES_PASSWORD` | Beliebiges sicheres Passwort für PostgreSQL |
| `EMBEDDING_BASE_URL` | Ollama-URL für die Ingestion (Standard: `http://localhost:11434/v1`) |
| `EMBEDDING_MODEL` | Embedding-Modell (Standard: `nomic-embed-text`) |
| `MCP_DEFAULT_TOP_K` | Anzahl zurückgegebener Chunks pro Suche (Standard: `5`) |
| `CHUNK_SIZE` | Max. Zeichen pro Chunk (Standard: `1500`) |
| `CHUNK_OVERLAP` | Überlappung zwischen Chunks in Zeichen (Standard: `150`) |
| `DATABASE_URL` | Verbindungs-URL für die Ingestion (s. unten) |

> Das LLM wird **nicht** in `.env` konfiguriert, sondern direkt in Open WebUI
> — siehe [Open WebUI einrichten](#open-webui-einrichten).

**`DATABASE_URL` für die Ingestion:**

Die Ingestion läuft direkt auf dem Host und verbindet sich über den exponierten Port mit
PostgreSQL. Den Wert in `.env` eintragen (Passwort aus `POSTGRES_PASSWORD` einsetzen):

```
DATABASE_URL=postgresql://retriever:<POSTGRES_PASSWORD>@localhost:5431/knowledge
```

> Der MCP-Server bekommt `DATABASE_URL` automatisch über `docker-compose.yml` gesetzt
> (Hostname `postgres` statt `localhost`) — dieser Wert muss **nicht** in `.env` stehen.

### 4. Ollama-Modell herunterladen

```bash
ollama pull nomic-embed-text
```

### 5. Ingestion-Abhängigkeiten installieren

```bash
cd ingestion
uv sync
cd ..
```

Erstellt `ingestion/.venv/` — keine globale Python-Installation nötig.

---

## Stack starten

```bash
docker compose up -d
```

Startet PostgreSQL (mit automatischer Schema-Initialisierung) und den MCP-Server.
Beim ersten Start wird das MCP-Server-Image gebaut (`docker compose up -d --build`).

Status prüfen:

```bash
docker compose ps
docker compose logs mcp-server
```

---

## Wissen einlesen (Ingestion)

**Voraussetzung:** `DATABASE_URL` muss in `.env` gesetzt sein (siehe [Umgebungsvariablen](#2-umgebungsvariablen-konfigurieren)).
Der Docker-Stack (`docker compose up -d`) muss laufen, damit PostgreSQL erreichbar ist.

```bash
cd ingestion
uv run python src/run.py --source wikipedia_ai
```

Das Skript liest alle in `sources.yaml` für die Quelle `wikipedia_ai` definierten Seiten,
chunked den Text, erzeugt Embeddings via Ollama und schreibt alles in PostgreSQL.

Bereits eingelesene, unveränderte Dokumente werden übersprungen (SHA-256-Prüfung) —
das Skript kann beliebig oft erneut ausgeführt werden.

Ausgabe-Beispiel:
```
[wikipedia_ai] Starting ingestion (type=wikipedia)
  Fetching: Artificial_intelligence
  Processing: Artificial intelligence
    42 chunks — generating embeddings...
    updated
  ...
[wikipedia_ai] Done: 8 processed, 8 updated/inserted
```

---

## Open WebUI einrichten

### 1. LLM konfigurieren

Das LLM wird direkt in Open WebUI konfiguriert — nicht über `.env`.

**Admin Panel → Settings → Connections → OpenAI API** → neue Verbindung hinzufügen. Beispiel für Groq und Gemini:

| | Groq | Google Gemini Flash |
|---|---|---|
| **Registrierung** | [console.groq.com](https://console.groq.com) | [aistudio.google.com](https://aistudio.google.com) |
| **API Base URL** | `https://api.groq.com/openai/v1` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| **API Key** | `gsk_...` | `AIza...` |
| **Modell** | `llama-3.3-70b-versatile` | `gemini-2.5-flash` |

Beide Anbieter sind kostenlos nutzbar (mit Limits).

### 2. Tool-Server verbinden

Open WebUI erwartet einen OpenAPI-kompatiblen Tool-Server. `mcpo` übersetzt das MCP-Protokoll
in OpenAPI und läuft als eigener Container im Docker-Stack.

**Settings → Integrations → Manage Tool Servers** → neuen Server hinzufügen:
- URL: `http://localhost:8081/knowledge-retriever`
- Kein API-Key nötig

### 3. Tools für das Modell aktivieren

In Open WebUI werden Tools zu Modellen hinzugefügt:

**Admin Panel → Settings → Models** → gewünschtes Modell bearbeiten → ai-knowledge-retriever aktivieren

---

## Neue Datenquelle hinzufügen

1. Eintrag in `sources.yaml` ergänzen:
   ```yaml
   - slug: meine_quelle
     display_name: "Meine Quelle"
     type: wikipedia           # oder ein neuer Connector-Typ
     config:
       language: de
       pages:
         - Mein_Thema
   ```

2. Ingestion ausführen:
   ```bash
   cd ingestion
   uv run python src/run.py --source meine_quelle
   ```

3. MCP-Server neu starten (liest `sources.yaml` beim Start):
   ```bash
   docker compose restart mcp-server
   ```

Ein neues Tool `search_meine_quelle` steht danach in Open WebUI zur Verfügung.

Für einen eigenen Connector-Typ: `ingestion/src/connectors/` — neue Klasse, die
`BaseConnector` erbt und `fetch_documents()` als async generator implementiert.
Anschliessend in `CONNECTOR_MAP` in `run.py` registrieren.

---

## Projektstruktur

```
ai-knowledge-retriever/
├── sources.yaml              # Datenquellen-Konfiguration (gitignored – aus sources.yaml.example erstellen)
├── sources.yaml.example      # Versioniertes Template ohne vertrauliche Werte
├── .env.example              # Vorlage für Umgebungsvariablen
├── docker-compose.yml        # PostgreSQL + MCP-Server
├── db/
│   └── init.sql              # Datenbankschema (wird beim ersten Start ausgeführt)
├── mcp-server/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── main.py           # Startup, dynamische Tool-Registrierung
│       ├── search.py         # Vektorsuche, Ergebnis-Aufbereitung
│       ├── db.py             # asyncpg-Verbindungspool
│       └── embedder.py       # Ollama-Embedding-Client (async)
└── ingestion/
    ├── pyproject.toml
    └── src/
        ├── run.py            # Einstiegspunkt, Pipeline-Orchestrierung
        ├── chunker.py        # Satzgrenzen-basiertes Chunking mit Overlap
        ├── embedder.py       # Ollama-Embedding-Client (sync, Batch)
        ├── db.py             # psycopg3-Datenbankzugriff, upsert-Logik
        └── connectors/
            ├── base.py       # Abstrakte Basisklasse für Connectoren
            └── wikipedia.py  # Wikipedia-Connector (HTML-Parsing via BeautifulSoup)
```
