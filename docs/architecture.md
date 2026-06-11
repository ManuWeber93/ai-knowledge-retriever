# AI Knowledge Retriever – Architekturdokumentation

**Version:** 0.3 (MVP)  
**Datum:** 2026-06-11  
**Status:** MVP implementiert

---

## 1. Überblick

Das System ist eine RAG-Plattform (Retrieval Augmented Generation), die Unternehmenswissen aus
verschiedenen Quellen in einer Vektor-Datenbank vorhält und über einen MCP-Server abrufbar macht.
Ein konfigurierbares LLM-Backend (Groq, OpenAI-kompatibel) beantwortet Nutzeranfragen angereichert
mit kontextrelevanten Dokumenten.

**MVP-Scope:** Wikipedia als erste Datenquelle, Groq als Cloud-LLM, nomic-embed-text für Embeddings.
Open WebUI und Ollama laufen lokal und sind nicht Bestandteil des Docker-Compose-Stacks.

---

## 2. Komponentendiagramm

```
┌──────────────────────────────────────────────────────────────────┐
│               LLM Provider (OpenAI-kompatibel)                   │
│   Groq  /  Google Gemini Flash  /  andere OpenAI-komp. APIs      │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ HTTP (OpenAI API)
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│            Open WebUI  (lokal, kein Docker)                      │
│   Chat-Interface – verbindet LLM-Provider und MCP-Server         │
└──────────────────────────────────┬───────────────────────────────┘
                                   │ MCP Protocol (HTTP/SSE, Port 8000)
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│              MCP Server  (Python / FastMCP, Docker)              │
│                                                                   │
│   Dynamische Tool-Registrierung aus sources.yaml:                │
│   Pro Source ein Tool  →  search_{slug}(query, top_k)            │
│                                                                   │
│   MVP:         search_wikipedia_ai                               │
│   Phase 1:     search_notes_{name}  /  search_wiki_intern        │
│                                                                   │
│   Authentifizierung: im MVP offen – Phase 1: API-Key (Bearer)    │
└──────────────────────────────────┬───────────────────────────────┘
                                   │ SQL + pgvector (Port 5432)
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│         PostgreSQL 16 + pgvector  (Docker)                       │
│   sources  →  documents  →  chunks (vector(768))                 │
└──────────────────────────────────┬───────────────────────────────┘
                                   │  befüllt durch
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│           Ingestion Pipeline  (Python / uv, läuft auf Host)      │
│                                                                   │
│   Wikipedia Connector            (zukünftig: MediaWiki, Notes)   │
│       ↓  HTML abrufen (httpx) + bereinigen (BeautifulSoup)       │
│       ↓  Chunking (~1500 Zeichen, 150 Zeichen Overlap)           │
│       ↓  Embedding via Ollama / nomic-embed-text (lokal)         │
│       ↓  Upsert in PostgreSQL (Δ-Erkennung via SHA-256)          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Technologie-Entscheidungen

### 3.1 Chat-Interface: Open WebUI

Lokal installiert (Desktop App oder Docker-Instanz des Nutzers).

| Kriterium | Bewertung |
|-----------|-----------|
| OpenAI-API-kompatibel | ✅ |
| MCP-Tool-Integration | ✅ Tool-Endpoint konfigurierbar |
| Self-hostbar | ✅ |
| Benutzerverwaltung | ✅ |

Konfiguration: LLM Base URL → Groq-Endpunkt, MCP-Server → `http://localhost:8000/sse`

---

### 3.2 LLM-Backend: Gratis Cloud (OpenAI-kompatibel)

Beide Optionen sind vollständig OpenAI-API-kompatibel — kein Code-Unterschied.

| Provider | Base URL | Modell | Gratis-Kontingent |
|----------|----------|--------|-------------------|
| **Groq** (empfohlen) | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | 14.400 Req/Tag |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.5-flash` | 1 Mio. Tokens/Tag |

---

### 3.3 Vektor-Datenbank: PostgreSQL + pgvector

- Docker Image: `pgvector/pgvector:pg16`
- Vektordimensionen: **768** (nomic-embed-text)
- Index: HNSW (Approximate Nearest Neighbor, schneller als exakte Suche bei großen Datasets)

---

### 3.4 MCP-Server: FastMCP (Python)

**Jede konfigurierte Datenquelle erhält ein eigenes MCP-Tool.** Der Tool-Name wird beim
Serverstart dynamisch aus dem `slug`-Feld in `sources.yaml` generiert:

```python
# Für sources.yaml-Eintrag mit slug="wikipedia_ai":
async def search_wikipedia_ai(query: str, top_k: int = 5) -> list[dict]:
    """Search 'Wikipedia – AI Articles' for relevant text passages..."""
    # Gibt zurück: [{text, title, url, score}, ...]
```

Neue Datenquellen werden durch einen Eintrag in `sources.yaml` aktiviert — kein Code-Change.

**Authentifizierung:** Im MVP ist der MCP-Server offen zugänglich (keine Auth). Da er lokal
läuft, ist dies für die MVP-Phase akzeptabel. Phase 1 ergänzt API-Key-Authentifizierung
via Bearer Token in FastMCP.

---

### 3.5 Ingestion: Python (ohne Framework)

| Komponente | Tool |
|-----------|------|
| HTTP-Requests | `httpx` (async) |
| HTML bereinigen | `beautifulsoup4` |
| Chunking | Eigene Implementierung (Sentence-Boundary-aware) |
| Embedding | `httpx` → Ollama `/v1/embeddings` |
| DB-Zugriff | `psycopg[binary]` v3 + `pgvector` |
| Dependency-Management | `uv` + `pyproject.toml` |

---

### 3.6 Embedding: nomic-embed-text

| Eigenschaft | Wert |
|-------------|------|
| Modell | `nomic-embed-text` |
| Anbieter | Ollama (lokal, kein GPU nötig) |
| Dimensionen | **768** |
| Kontext | 8.192 Tokens |
| Setup | `ollama pull nomic-embed-text` |

Das Embedding-Modell muss bei Ingestion und Query-Zeit identisch sein.
Ein Modellwechsel erfordert vollständige Re-Indizierung aller Chunks.

---

## 4. Datenmodell

### 4.1 ERD

```mermaid
erDiagram
    sources {
        uuid    id           PK
        string  slug
        string  display_name
        string  type
        jsonb   config
        ts      last_sync
        ts      created_at
    }

    documents {
        uuid    id                 PK
        uuid    source_id          FK
        uuid    parent_document_id FK "nullable"
        string  external_id
        string  title
        text    content
        string  url
        jsonb   metadata
        string  content_hash
        ts      indexed_at
    }

    chunks {
        uuid    id           PK
        uuid    document_id  FK
        int     chunk_index
        text    text
        vector  embedding
        int     token_count
        ts      created_at
    }

    sources   ||--o{ documents : "enthält"
    documents ||--o{ documents : "hat Anhänge"
    documents ||--o{ chunks   : "wird aufgeteilt in"
```

### 4.2 Entitäten

**`sources`** — Registry aller konfigurierten Datenquellen

| Feld | Bedeutung |
|------|-----------|
| `slug` | Technischer Bezeichner; wird direkt zu MCP-Tool-Name (`search_{slug}`) |
| `type` | Bestimmt welcher Connector verwendet wird: `wikipedia` \| `mediawiki` \| `hcl_notes` |
| `config` | JSONB — source-spezifische Parameter (Seiten-Liste, Base-URL, View-Namen). Kein Schema-Change bei neuen Source-Typen nötig. |
| `last_sync` | Zeitstempel des letzten Laufs — Basis für spätere inkrementelle Synchronisation |

---

**`documents`** — Ein Eintrag pro Quelldokument oder Anhang (Wikipedia-Artikel, Notes-Dokument, Wiki-Seite, PDF-Anhang, …)

| Feld | Bedeutung |
|------|-----------|
| `parent_document_id` | `NULL` bei eigenständigen Dokumenten. Zeigt bei Anhängen auf das übergeordnete Dokument. CASCADE DELETE: wird ein Elterndokument gelöscht, verschwinden seine Anhänge automatisch. |
| `external_id` | Quellsystem-ID (Wikipedia-Titel, Notes-UNID, Dateiname). Zusammen mit `source_id` UNIQUE → idempotente Re-Ingestion ohne Duplikate |
| `content` | Volltext — ermöglicht Re-Chunking bei Strategieänderung ohne erneuten API-Abruf |
| `url` | Direktlink zurück zur Quelle — das LLM kann Antworten mit Quellnachweisen belegen |
| `metadata` | JSONB — flexible source-spezifische Felder (Kategorien, Autor, Datum, Tags, Dateityp) |
| `content_hash` | SHA-256 des Inhalts — bei Re-Ingestion wird ein Dokument übersprungen, wenn sich der Hash nicht geändert hat |

---

**`chunks`** — Die eigentliche Sucheinheit (Teilstücke eines Dokuments)

| Feld | Bedeutung |
|------|-----------|
| `chunk_index` | Position im Dokument — ermöglicht Rekonstruktion von Nachbar-Chunks für erweiterten Kontext |
| `embedding` | `vector(768)` — nomic-embed-text Vektor, per HNSW-Index indiziert |
| `token_count` | Vorberechnete Tokenzahl — für LLM-Kontextfenster-Budgetierung |

Dokumente werden in Chunks aufgeteilt, da Embedding-Modelle und Retrieval bei kurzen,
semantisch fokussierten Textstücken (~300–500 Tokens) präziser arbeiten als bei langen Dokumenten.

---

## 5. Konfiguration (.env)

Basiert auf `.env.example`. Zwei Kontexte mit unterschiedlichen URLs:

```bash
# PostgreSQL
POSTGRES_PASSWORD=changeme

# LLM – nur für Open WebUI relevant (nicht vom MCP-Server verwendet)
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile

# Embeddings via lokales Ollama
# MCP-Server (in Docker → greift über Bridge auf Host-Ollama zu):
EMBEDDING_BASE_URL=http://host.docker.internal:11434/v1
# Ingestion-Skript (läuft auf Host):
#   EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_API_KEY=ollama

# DB-Verbindung für Ingestion-Skript (läuft auf Host):
DATABASE_URL=postgresql://retriever:changeme@localhost:5432/knowledge

# MCP-Server Suchverhalten
MCP_DEFAULT_TOP_K=5       # Anzahl zurückgegebener Chunks pro Suche

# Ingestion Chunking
CHUNK_SIZE=1500            # Max. Zeichen pro Chunk
CHUNK_OVERLAP=150          # Overlap zwischen aufeinanderfolgenden Chunks
```

---

## 6. Ingestion-Pipeline

### 6.1 Wikipedia Connector (MVP)

Öffentliche Wikipedia REST API, keine Authentifizierung:

```
GET https://en.wikipedia.org/api/rest_v1/page/html/{title}
```

Ablauf:
1. HTML abrufen, Tabellen/Referenzen/Navigations-Elemente entfernen (BeautifulSoup)
2. Plaintext extrahieren
3. In Chunks aufteilen (~1.500 Zeichen, 150 Zeichen Overlap, Satzgrenzen-aware)
4. Pro Chunk: Embedding via Ollama `nomic-embed-text`
5. Upsert in PostgreSQL — Skip wenn `content_hash` unverändert

### 6.2 Anhänge (quellenübergreifend)

Jeder Connector kann Anhänge als eigenständige Dokumente liefern. Das Ingestion-Skript
verknüpft sie über `parent_document_id` mit dem Elterndokument:

- Connector setzt `parent_external_id` im yielded dict des Anhangs
- `run.py` löst `parent_external_id` → DB-`id` auf (der Parent muss zuerst geyieldet werden)
- Anhang wird als eigenes `documents`-Eintrag mit gesetztem `parent_document_id` gespeichert
- Chunks des Anhangs werden normal indiziert; die Suche gibt bei Treffern zusätzlich `parent_title` und `parent_url` zurück

Unterstützte Anhang-Typen hängen vom jeweiligen Connector ab. Für die Textextraktion aus
Binärformaten (PDF, DOCX) werden in Phase 1 Libraries wie `pypdf` / `python-docx` ergänzt.

### 6.3 MediaWiki Connector (Phase 1)

Internes Wiki erfordert Authentifizierung. Empfohlener Ansatz: **MediaWiki Bot-Passwort**

```
POST /w/api.php?action=login&lgname=BotUser@bot-name&lgpassword=...
```

Credentials in `.env`: `MEDIAWIKI_BOT_USER`, `MEDIAWIKI_BOT_PASSWORD`

### 6.4 HCL Notes Connector (Phase 2)

Empfohlener Ansatz: **Domino Access Services (DAS) REST API**

```
GET /api/data/collections/name/{viewname}
GET /api/data/documents/{unid}
```

Voraussetzung: Domino HTTP-Task aktiviert, DAS-Plugin installiert.
Alternativ: DXL-Export (XML) via Notes-Client-Skript.

Anhänge: Notes-Dokumente können Dateianhänge enthalten. Der Connector listet diese via
`/$file`-Endpunkt und yieldet sie mit `parent_external_id` gesetzt.

---

## 7. Projektstruktur

```
ai-knowledge-retriever/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── sources.yaml              # Datenquellen-Definitionen – gitignored (kann vertrauliche Angaben enthalten)
├── sources.yaml.example      # Versioniertes Template ohne sensible Werte
│
├── db/
│   └── init.sql              # Schema + pgvector Extension
│
├── mcp-server/
│   ├── Dockerfile
│   ├── pyproject.toml        # Dependencies (uv)
│   └── src/
│       ├── main.py           # FastMCP Startup + dynamische Tool-Registrierung
│       ├── db.py             # asyncpg Connection Pool
│       ├── embedder.py       # Ollama Embedding API (async)
│       └── search.py         # Vektorsuche (cosine similarity via pgvector)
│
├── ingestion/
│   ├── pyproject.toml        # Dependencies (uv)
│   └── src/
│       ├── run.py            # Einstiegspunkt: uv run python src/run.py --source <slug>
│       ├── chunker.py        # Text → überlappende Chunks
│       ├── embedder.py       # Ollama Embedding API (sync)
│       ├── db.py             # psycopg v3 Upsert
│       └── connectors/
│           ├── base.py
│           └── wikipedia.py
│
└── architecture.md
```

---

## 8. Entwicklungs-Roadmap

### MVP (abgeschlossen)
- [x] Architektur definieren und dokumentieren
- [x] Docker-Compose Setup (PostgreSQL + pgvector + MCP-Server)
- [x] Datenbankschema implementieren
- [x] MCP-Server mit dynamischer Tool-Registrierung (FastMCP)
- [x] Ingestion-Pipeline: Wikipedia Connector
- [x] Dependency-Isolation via `uv` + `pyproject.toml`
- [x] Ollama: `ollama pull nomic-embed-text`
- [x] `.env` aus `.env.example` erstellen und befüllen
- [ ] `docker compose up -d`
- [ ] Wikipedia indexieren:
  ```bash
  cd ingestion
  uv sync --no-install-project
  uv run python src/run.py --source wikipedia_ai
  ```
- [ ] Open WebUI: Groq als LLM + MCP-Server `http://localhost:8000/sse` als Tool

### Phase 1
- [ ] MediaWiki Connector (Bot-Passwort-Auth)
- [ ] API-Key-Authentifizierung im MCP-Server (Bearer Token via FastMCP)
- [ ] Inkrementelle Synchronisation (nur geänderte Dokumente, nutzt `last_sync`)

### Phase 2
- [ ] HCL Notes Connector (Domino Access Services)

### Phase 3
- [ ] Hybridsuche (Vektor + Volltext, RRF-Kombination)
- [ ] Re-ranking der Ergebnisse (Cross-Encoder)
- [ ] Monitoring (OpenTelemetry)
- [ ] Admin-UI für Quellenverwaltung

### Phase 4
- [ ] Per-User-Zugriffskontrolle (User-Identity-Propagation)
  - Neue DB-Tabelle `source_permissions` (Rolle → erlaubte Sources)
  - Bearer-Token-Propagation: Open WebUI → mcpo → MCP-Server
  - Custom Middleware im MCP-Server: Token validieren, `source_slug` gegen Berechtigungen prüfen
  - Details siehe [Abschnitt 10](#10-zugriffskontrolle-phase-4)

---

## 10. Zugriffskontrolle (Phase 4)

### 10.1 Ziel

Jeder Nutzer darf nur die Datenquellen abfragen, für die er berechtigt ist. Die Durchsetzung
erfolgt im MCP-Server — unabhängig vom Chat-Interface. Ein Nutzer, der den MCP-Server direkt
anspricht (z.B. via curl), erhält dieselbe Zugriffskontrolle wie über Open WebUI.

### 10.2 Ablauf

```
Open WebUI
  │  Authorization: Bearer <user-token>
  ▼
mcpo  (leitet Header unverändert weiter)
  │  Authorization: Bearer <user-token>
  ▼
MCP-Server  (FastMCP Custom Middleware)
  │  1. Token verifizieren → user_id / Rolle ermitteln
  │  2. Angefragten source_slug gegen source_permissions prüfen
  │  3a. Berechtigt   → Tool ausführen
  │  3b. Nicht ber.  → HTTP 403
```

### 10.3 Datenbankschema (Erweiterung)

Neue Tabelle `source_permissions` neben dem bestehenden Schema:

```sql
CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,   -- z.B. "intern-basic", "intern-full"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_permissions (
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    source_id   UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, source_id)
);

-- Nutzer-Rolle-Zuordnung (falls nicht aus dem Token ableitbar)
CREATE TABLE user_roles (
    user_id     TEXT NOT NULL,          -- Wert aus dem Bearer Token (sub-Claim)
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);
```

### 10.4 Token-Validierung

Open WebUI stellt beim Tool-Aufruf einen Bearer Token bereit. Der MCP-Server validiert ihn
über eine der folgenden Strategien (je nach Auth-Infrastruktur):

| Strategie | Wann sinnvoll |
|-----------|---------------|
| **Shared Secret / API-Key** | Einfachste Variante; ein Key pro Rolle, in DB hinterlegt |
| **JWT (selbst signiert)** | Open WebUI signiert Token mit privatem Schlüssel; MCP-Server prüft Signatur mit Public Key |
| **OIDC / OAuth 2.0** | Wenn ein zentraler Identity Provider (Keycloak, Azure AD) vorhanden ist |

Für Phase 4 empfohlen: **JWT mit RS256** — Open WebUI als Token-Aussteller, MCP-Server als
Resource Server. Der `sub`-Claim enthält die `user_id`, ein custom Claim `roles` die Rollenliste.

### 10.5 FastMCP Middleware

FastMCP erlaubt das Einbinden von ASGI-Middleware. Die Autorisierungslogik wird als
`AuthorizationMiddleware` implementiert, die vor jedem Tool-Aufruf:

1. `Authorization`-Header ausliest
2. Token verifiziert (Signatur, Ablauf)
3. `user_id` und `roles` aus dem Token extrahiert
4. Den angefragten `source_slug` gegen `source_permissions` in der DB prüft
5. Bei fehlender Berechtigung HTTP 403 zurückgibt — bevor das Tool ausgeführt wird

Der `source_slug` ergibt sich aus dem Tool-Namen: `search_{slug}` → `slug`.

---

## 9. Technologie-Übersicht

| Komponente | Technologie | Version |
|-----------|-------------|---------|
| Chat-Interface | Open WebUI | lokal |
| LLM (Cloud, gratis) | Groq / `llama-3.3-70b-versatile` | – |
| MCP-Server | FastMCP (Python) | ≥ 2.0 |
| Vektor-DB | PostgreSQL 16 + pgvector | pg16 / ≥ 0.7 |
| Embedding | nomic-embed-text via Ollama | – |
| Ingestion | Python 3.12, httpx, beautifulsoup4 | – |
| Dependency-Management | uv | – |
| Containerisierung | Docker + Docker Compose | ≥ 27 |
