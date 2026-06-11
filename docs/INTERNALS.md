# Code-Internals: Wie das System funktioniert

Dieses Dokument beschreibt den konkreten Ablauf des Codes und das Zusammenspiel der Komponenten.
Die übergeordnete Architektur ist in `architecture.md` dokumentiert.

---

## 1. Konfigurationszentrale: `sources.yaml`

Alles beginnt mit `sources.yaml`. Diese Datei beschreibt alle Wissensquellen und ist in
`.gitignore` aufgenommen — `sources.yaml.example` dient als versioniertes Template.

```yaml
sources:
  - slug: wikipedia_ai          # wird zum DB-Schlüssel und zum MCP-Tool-Namen
    display_name: "Wikipedia – AI Articles"
    type: wikipedia             # bestimmt welcher Connector geladen wird
    config:                     # wird 1:1 an den Connector übergeben
      language: en
      pages:
        - Artificial_intelligence
```

Beide Komponenten (Ingestion und MCP-Server) lesen dieselbe Datei — aber unabhängig voneinander.

---

## 2. Ingestion-Pipeline

### 2.1 Einstiegspunkt: `ingestion/src/run.py`

```
python src/run.py --source wikipedia_ai
```

**`main()`** liest `sources.yaml`, findet den angeforderten Source-Eintrag per `slug` und übergibt
ihn an `asyncio.run(run_ingestion(source_config))`.

**`run_ingestion(source_config)`** ist das Herzstück der Pipeline:

1. Liest `slug`, `display_name`, `type` und `config` aus dem Source-Eintrag.
2. Schlägt den passenden Connector in `CONNECTOR_MAP` nach (`"wikipedia"` → `WikipediaConnector`, `"web"` → `WebConnector`).
3. Öffnet eine DB-Verbindung und stellt via `get_or_create_source()` sicher, dass die Source
   in der `sources`-Tabelle existiert (INSERT ON CONFLICT).
4. Iteriert asynchron über alle Dokumente des Connectors.
5. Pro Dokument: chunken → embedden → in DB schreiben.
6. Führt ein `inserted_ids`-Dict (`external_id → db_uuid`), das für Anhang-Verlinkung benötigt wird.

### 2.2 Connector: `ingestion/src/connectors/wikipedia.py`

`WikipediaConnector.fetch_documents()` ist ein **async generator** (yield statt return):

1. Holt `language` und `pages`-Liste aus dem config-Dict.
2. Öffnet einen `httpx.AsyncClient` für alle Requests dieser Source.
3. Ruft pro Seite `_fetch_page()` auf und yieldet das Ergebnis-Dict.

**`_fetch_page()`** macht folgendes:
1. GET auf die Wikipedia REST API (`/api/rest_v1/page/html/{title}`) — liefert HTML.
2. Parst das HTML mit BeautifulSoup.
3. Entfernt Rauschen: `<table>`, `<figure>`, `<sup>` und CSS-Klassen wie `navbox`, `reflist`.
4. Extrahiert den reinen Text aus `<body>` und filtert Leerzeilen.
5. Gibt ein normiertes Dict zurück:
   ```python
   {"external_id": title, "title": ..., "content": ..., "url": ..., "metadata": {...}}
   ```

Das Dict folgt dem Vertrag aus `BaseConnector` (Docstring in `connectors/base.py`).
Anhänge würden zusätzlich `parent_external_id` enthalten.

### 2.3 Connector: `ingestion/src/connectors/web.py`

`WebConnector` ist ein generischer Connector für beliebige Webseiten. Die zu ingestierenden
URLs werden manuell in `sources.yaml` unter `config.urls` angegeben.

**`_fetch_page()`** macht folgendes:
1. GET auf die angegebene URL.
2. Parst das HTML mit BeautifulSoup.
3. Entfernt Rauschen: `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<form>`, `<iframe>`.
4. Sucht den Hauptinhalt in `<main>` → `<article>` → `<body>` (erste Übereinstimmung).
5. Extrahiert den Titel aus `<h1>` (bevorzugt) oder `<title>`.
6. Gibt ein normiertes Dict zurück (URL dient als `external_id`).

### 2.3 Chunker: `ingestion/src/chunker.py`

`chunk_text(text, max_chars, overlap_chars)` teilt langen Text in überlappende Abschnitte:

1. Splittet den Text an Satzgrenzen (`(?<=[.!?])\s+`).
2. Füllt einen `current`-Buffer mit Sätzen auf, bis `max_chars` überschritten würde.
3. Schreibt den Buffer als Chunk, dann berechnet er den **Overlap**:
   — iteriert `current` rückwärts, nimmt Sätze herein, solange `overlap_chars` nicht überschritten.
   — diese Sätze (`overlap_sentences`) bilden den Anfang des nächsten Chunks.
4. Filtert am Ende Chunks unter `_MIN_CHUNK_CHARS = 50` Zeichen heraus.

Ergebnis: semantisch zusammenhängende Abschnitte mit Kontext-Überlappung zwischen benachbarten Chunks.

### 2.4 Embedder (Ingestion): `ingestion/src/embedder.py`

`get_embeddings(texts)` sendet eine Batch-Anfrage an die Ollama-API (OpenAI-kompatibel):

```
POST http://localhost:11434/v1/embeddings
{"model": "nomic-embed-text", "input": ["text1", "text2"]}
```

`nomic-embed-text` liefert 768-dimensionale Float-Vektoren.
Die Antwort wird nach `index` sortiert (API-Garantie, defensiv), bevor die Vektoren zurückgegeben werden.
`get_embedding(text)` ist eine Hilfsfunktion für Einzel-Texte.

### 2.5 Datenbank (Ingestion): `ingestion/src/db.py`

**`get_or_create_source()`**: Prüft ob `slug` schon in `sources` existiert. Falls ja → gibt die ID zurück.
Falls nein → INSERT mit `display_name`, `type`, `config` (als JSONB).

**`upsert_document()`** — der komplexeste Teil:
1. Berechnet SHA-256-Hash des Inhalts.
2. Sucht das Dokument in `documents` per `(source_id, external_id)`.
3. **Unverändert** (Hash gleich): gibt `(False, doc_id)` zurück — kein erneutes Chunken/Embedden.
4. **Geändert** (Hash verschieden): UPDATE des Dokuments + DELETE aller alten Chunks.
5. **Neu**: INSERT des Dokuments, bekommt neue UUID.
6. Schreibt alle Chunks mit ihren Embeddings in die `chunks`-Tabelle.
7. Setzt dabei `parent_document_id` wenn übergeben (für Anhänge).
8. Gibt `(True, doc_id)` zurück.

### 2.6 Anhang-Mechanismus

Connectors können Anhänge modellieren, indem sie `parent_external_id` im Dokument-Dict setzen.
`run_ingestion()` löst diese externe ID zur DB-UUID auf:

```python
inserted_ids: dict[str, str]  # external_id → db-uuid

# Beim Verarbeiten eines Anhangs:
if parent_external_id := doc.get("parent_external_id"):
    parent_doc_id = inserted_ids.get(parent_external_id)
```

**Wichtig**: Der Connector muss das Eltern-Dokument vor seinen Anhängen yielden, da die UUID
noch nicht existiert, bevor das Eltern-Dokument in die DB geschrieben wurde.

---

## 3. MCP-Server

### 3.1 Startup: `mcp-server/src/main.py`

Beim Start des Servers (Modul wird importiert) wird `_register_source_tools()` aufgerufen:

1. Liest `sources.yaml` (Pfad via `SOURCES_PATH`-Env, Default: `/app/sources.yaml`).
2. Für jede Source: ruft `_register_source_tool(slug, display_name)` auf.

**`_register_source_tool()`** erzeugt dynamisch ein MCP-Tool:

```python
async def search(query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    return await search_chunks(slug, query, top_k)

search.__name__ = f"search_{slug}"   # → z.B. "search_wikipedia_ai"
search.__doc__  = "..."              # wird dem LLM als Tool-Beschreibung angezeigt
mcp.tool()(search)                   # registriert die Funktion bei FastMCP
```

Der Trick mit `__name__` und `__doc__` ist nötig, weil FastMCP den Funktionsnamen als Tool-Namen
und den Docstring als Beschreibung verwendet — und closure-Funktionen sonst alle `search` heissen würden.

### 3.2 Tool-Ausführung: `mcp-server/src/search.py`

Wenn ein LLM (z.B. via Open WebUI) das Tool `search_wikipedia_ai` aufruft:

1. **Embedden der Suchanfrage**: `get_embedding(query)` — gleicher Ollama-Endpoint,
   aber async (`httpx.AsyncClient`) und einzelner Text statt Batch.
2. **Vektorsuche**: SQL-Query gegen `chunks` + `documents` + `sources`:
   ```sql
   SELECT c.text, d.title, d.url, parent.title AS parent_title, parent.url AS parent_url,
          1 - (c.embedding <=> $1::vector) AS score
   FROM chunks c
   JOIN documents d ON c.document_id = d.id
   LEFT JOIN documents parent ON d.parent_document_id = parent.id
   JOIN sources s ON d.source_id = s.id
   WHERE s.slug = $2
   ORDER BY c.embedding <=> $1::vector   -- cosine distance aufsteigend = similarity absteigend
   LIMIT $3
   ```
   Der HNSW-Index auf `chunks.embedding` macht diese Suche effizient (approximate nearest neighbor).
3. **Ergebnis-Aufbereitung**: Pro Zeile wird ein Dict gebaut. Wenn das Dokument ein Anhang ist
   (`parent_title IS NOT NULL`), werden `parent_title` und `parent_url` ergänzt, damit das LLM
   korrekte Quellenangaben machen kann.

### 3.3 DB-Pool: `mcp-server/src/db.py`

`get_pool()` implementiert einen lazy Singleton: beim ersten Aufruf wird ein asyncpg-Verbindungspool
erstellt (2–10 Verbindungen), bei allen weiteren Aufrufen wird der bestehende Pool zurückgegeben.
`register_vector` wird als `init`-Callback übergeben, damit pgvector auf jeder neuen Verbindung
registriert wird.

---

## 4. Datenbankschema

Drei Tabellen, zwei Kardinalitäten:

```
sources  1──*  documents  1──*  chunks
              documents  0..1──*  documents   (self-reference: Anhänge)
```

| Tabelle     | Zweck                                                              |
|-------------|--------------------------------------------------------------------|
| `sources`   | Eine Zeile pro Datenquelle (wikipedia_ai, …); JSONB-Konfiguration |
| `documents` | Eine Zeile pro Seite/Dokument/Anhang; SHA-256-Hash für Idempotenz  |
| `chunks`    | Ein Abschnitt eines Dokuments; `embedding vector(768)` für Suche   |

Der HNSW-Index (`vector_cosine_ops`) auf `chunks.embedding` ist der Performance-kritische Teil:
ohne ihn würde jede Suche alle Vektoren vergleichen (sequential scan).

---

## 5. Laufzeit-Topologie

```
Open WebUI (lokal)
    │  MCP HTTP (SSE, Port 8000)
    ▼
mcp-server (Docker)
    │  asyncpg (Port 5432)         │  HTTP (Port 11434)
    ▼                              ▼
postgres (Docker)           Ollama (lokal, Host)
                            nomic-embed-text

ingestion (lokal, manuell)
    │  psycopg3 (Port 5432)        │  HTTP (Port 11434)
    ▼                              ▼
postgres (Docker)           Ollama (lokal, Host)
```

Der MCP-Server läuft in Docker und erreicht Ollama über `host.docker.internal:11434`
(in `docker-compose.yml` via `extra_hosts: host.docker.internal:host-gateway` konfiguriert).
Die Ingestion läuft direkt auf dem Host und spricht Ollama über `localhost:11434` an.

---

## 6. Datenpfad: von der Anfrage zur Antwort

```
Nutzer tippt Frage in Open WebUI
    → Open WebUI ruft MCP-Tool auf (z.B. search_wikipedia_ai)
    → mcp-server: query wird zu 768-dim Vektor (Ollama)
    → mcp-server: HNSW-Suche in postgres, top-k Chunks
    → mcp-server: gibt Liste von {text, title, url, score} zurück
    → Open WebUI: Chunks werden als Kontext in den LLM-Prompt eingebettet
    → LLM (Groq / Gemini) generiert Antwort mit Quellenangaben
    → Nutzer sieht Antwort
```

---

## 7. Neue Datenquelle hinzufügen

1. Neuen Connector in `ingestion/src/connectors/` anlegen (erbt von `BaseConnector`,
   implementiert `fetch_documents()` als async generator).
2. Connector in `CONNECTOR_MAP` in `run.py` registrieren.
3. Eintrag in `sources.yaml` hinzufügen (`slug`, `display_name`, `type`, `config`).
4. Ingestion ausführen: `uv run python src/run.py --source <slug>`.
5. MCP-Server neu starten — er liest `sources.yaml` beim Start und registriert automatisch
   ein neues Tool `search_<slug>`.
