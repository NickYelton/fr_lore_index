# Forgotten Realms Lore Index

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB)
![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-4169E1)
![pgvector](https://img.shields.io/badge/vectors-pgvector-6E4AFF)
![Local first](https://img.shields.io/badge/inference-local%20(Ollama)-555555)

The Forgotten Realms Lore Index is a local-first, citation-backed knowledge base of Forgotten Realms lore. It harvests articles and rules data from openly licensed sources and normalizes them into one provenance-tracked schema in PostgreSQL. You can query the result in three ways: ranked full-text search, fuzzy name matching, or natural-language questions answered by a retrieval-augmented model running entirely on your own hardware.

The current corpus covers **elvenkind**: the Seldarine and the other elven deities, the subraces of the Tel'Quessir, the elven realms past and present, and the history that connects them. The schema and ingestion pipeline aren't tied to any one species, so other peoples, regions and a campaign's own homebrew material can be added through configuration alone.

> **Unofficial fan project.** It is not affiliated with, endorsed, sponsored or approved by Wizards of the Coast. See [Data sources & licensing](#data-sources--licensing).

---

## Table of contents

- [Overview](#overview)
- [Features](#features)
- [Coverage](#coverage)
- [Technology stack](#technology-stack)
- [Architecture](#architecture)
- [Data model](#data-model)
- [Search](#search)
- [Question answering](#question-answering)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Usage](#usage)
- [Extending the index](#extending-the-index)
- [Testing & evaluation](#testing--evaluation)
- [Project structure](#project-structure)
- [Data sources & licensing](#data-sources--licensing)
- [Responsible access](#responsible-access)
- [Known limitations](#known-limitations)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Overview

Forgotten Realms lore is spread across five decades of sourcebooks, novels and magazine articles, and nearly every edition of Dungeons & Dragons has revised it. Community wikis have cataloged much of this material, but a wiki is built to be read one page at a time. It can't answer a question that draws on many pages, filter claims by edition, or feed a campaign-planning tool.

The Lore Index turns that material into a structured, queryable corpus:

- **One schema for very different sources.** Wiki articles, Wikipedia's out-of-universe coverage, SRD rules data and personal homebrew notes are all stored as *documents* made of *passages*, with the same fields and the same guarantees.
- **Provenance on every record.** Each passage traces back to its source, URL, revision, license and retrieval time. Every search result and every generated answer can be cited and attributed.
- **Search tuned to the setting.** Queries handle diacritics (*Faerûn*), apostrophes and hyphens (*Tel'Quessir*, *Tel-quessir*), elven alternate names, and misspellings of deity and place names.
- **Answers grounded in sources.** The question-answering layer retrieves passages first and answers only from them, citing each claim. When the corpus doesn't cover a question, it says so.
- **Local-first.** The database, the embedding model and the language model all run on your machine. Queries and homebrew material never leave it.

The project is aimed at game masters and worldbuilders who want a private, searchable reference that keeps canon and homebrew side by side without mixing them up.

---

## Features

### Ingestion
- Discovers pages through the MediaWiki Action API, starting from seed categories. Subcategories are traversed recursively, cycles are detected, and continuation is followed until every page is listed.
- Seed pages can expand one hop along their links, filtered by infobox type. This collects every member of a pantheon without depending on how the wiki names its categories.
- Refreshes are incremental. Current revision IDs are checked in batches of up to 50 titles per request, and only changed pages are fetched again.
- Every API response is saved to the raw store before it's parsed. The whole corpus can be rebuilt from that store without any network access.
- The HTTP client is polite by default: it sends an identifying User-Agent, makes requests sequentially with throttling, uses `maxlag`, honors `Retry-After`, and backs off exponentially with jitter.

### Normalization
- Cleans HTML by removing navigation boxes, edit links, citation markers, galleries, tables of contents and appendix boilerplate.
- Extracts infoboxes into normalized JSONB, with snake_case keys and list-valued fields split into arrays.
- Splits articles into passages along their headings, keeping each passage's full heading path (e.g. `History › The Crown Wars`).
- Parses footnotes into structured sourcebook references (title, year, page) and tags every passage with the D&D editions its sources belong to.
- Records redirects as aliases, so a search for *Teu-Tel'Quessir* finds the *Moon elf* article.
- Validates every record against a Pydantic schema before it's written. Invalid records are rejected and reported, never stored.

### Search
- Weighted full-text search. Titles and aliases outrank headings and infobox values, which outrank body text.
- A custom text-search configuration makes matching insensitive to diacritics (`unaccent`) and maps irregular forms such as *elves* and *elven* to *elf* (a synonym dictionary).
- Trigram similarity on titles and aliases catches misspellings and powers "did you mean" suggestions.
- Supports web-style query syntax: quoted phrases, `or`, and `-exclusion`.
- Results can be filtered by document type, source and edition, and include highlighted snippets.

### Question answering (optional)
- Local embeddings generated through Ollama and stored in pgvector behind an HNSW index.
- Hybrid retrieval that fuses full-text and vector rankings with reciprocal rank fusion.
- Answers with numbered citations, each resolving to a URL, revision ID and license.
- When sources from different editions disagree, the answer reports the disagreement and cites both sides instead of silently picking one.
- A retrieval evaluation harness reports recall@k and mean reciprocal rank.

### Operations
- PostgreSQL and all required extensions run in a single Docker Compose service.
- Schema changes are versioned with Alembic migrations.
- A single `frlore` command-line tool covers ingestion, inspection, search, question answering and attribution.
- Every ingestion run is recorded with its counts of fetched, skipped and rejected pages.

---

## Coverage

The default configuration indexes the following areas of elven lore.

| Area | Examples |
|------|----------|
| **Pantheons and deities** | The Seldarine (Corellon Larethian, Aerdrie Faenya, Sehanine Moonbow, Labelas Enoreth, Solonor Thelandira, …) and the Dark Seldarine |
| **Subraces** | Sun, moon, wood, wild, sea and star elves, avariel, lythari, drow |
| **Realms and places** | Evermeet, Cormanthyr, Myth Drannor, Evereska, Aryvandaar, Illefarn, Eaerlann |
| **History** | The Crown Wars, the Retreat, the Descent of the Drow |
| **Notable figures** | Individual elves (off by default; see `include_characters`) |
| **Rules** | The Elf and High Elf species from SRD 5.1, and the Elf species from SRD 5.2 (via Open5e) |
| **Publication history** | How elves changed across editions (via Wikipedia) |

Document and passage counts depend on the configured crawl depth and on the current state of each wiki. Run `frlore stats` to see the totals for your index.

---

## Technology stack

| Layer | Technology | Role |
|-------|------------|------|
| Language | Python 3.12+ | All application code |
| HTTP | [httpx](https://www.python-httpx.org/), [tenacity](https://tenacity.readthedocs.io/) | API access with connection reuse, timeouts, retries and backoff |
| Parsing | [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) (lxml backend) | HTML cleaning, infobox extraction, section and footnote parsing |
| Validation | [Pydantic v2](https://docs.pydantic.dev/latest/), pydantic-settings | The record schema every source must produce, plus typed configuration |
| Database | [PostgreSQL 17](https://www.postgresql.org/docs/current/) | Storage, JSONB, full-text search |
| Extensions | `unaccent`, `pg_trgm`, [`pgvector`](https://github.com/pgvector/pgvector) | Diacritic folding, fuzzy matching, vector similarity |
| Data access | [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/), [psycopg 3](https://www.psycopg.org/psycopg3/docs/) | ORM models, transactional upserts, the PostgreSQL driver |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) | Versioned schema changes, including extensions and text-search configuration |
| CLI | [Typer](https://typer.tiangolo.com/) | The `frlore` command-line interface |
| Inference | [Ollama](https://github.com/ollama/ollama) | Local embedding and chat models |
| Infrastructure | [Docker Compose](https://docs.docker.com/compose/) | Reproducible local PostgreSQL with pgvector |
| Quality | [pytest](https://docs.pytest.org/) | Unit, integration and search-behavior tests |
| Tooling | [uv](https://docs.astral.sh/uv/) | Dependency management and task running |

---

## Architecture

### System overview

```mermaid
flowchart LR
    subgraph sources["Sources"]
        FR["Forgotten Realms Wiki"]
        WP["Wikipedia"]
        SW["Other setting wikis"]
        O5["Open5e API (SRD)"]
        HB["Homebrew Markdown"]
    end

    subgraph ingest["Ingestion"]
        MW["MediaWiki adapter"]
        OA["Open5e adapter"]
        LA["Local adapter"]
        HTTP["HTTP client<br/>User-Agent, throttling, retries"]
    end

    subgraph process["Processing"]
        PARSE["Parse and normalize<br/>Beautiful Soup"]
        VALID["Validate<br/>Pydantic"]
        LOAD["Upsert<br/>SQLAlchemy"]
    end

    subgraph pg["PostgreSQL"]
        RAW[("raw_payload")]
        CORE[("documents, passages,<br/>references, aliases")]
        IDX[("tsvector and trigram indexes")]
        VEC[("pgvector embeddings")]
    end

    subgraph query["Query"]
        SEARCH["Search<br/>full-text and fuzzy"]
        RAG["Hybrid retrieval<br/>and grounded answers"]
        CLI["frlore CLI"]
    end

    OLL["Ollama"]

    FR & WP & SW --> MW
    O5 --> OA
    MW & OA --> HTTP
    HTTP --> RAW
    HB --> LA --> RAW
    RAW --> PARSE --> VALID --> LOAD --> CORE
    CORE --- IDX
    CORE --> VEC
    OLL -. embeddings .-> VEC
    IDX --> SEARCH --> CLI
    IDX & VEC --> RAG --> CLI
    OLL -. generation .-> RAG
```

### Components

**Source adapters.** Each kind of source implements a small adapter interface: *discover* what exists, *fetch* it, and *parse* a raw payload into validated records. One `MediaWikiAdapter` serves every wiki (the Forgotten Realms Wiki, Wikipedia and any other MediaWiki site), configured per site. The `Open5eAdapter` walks the paginated Open5e v2 JSON API, and the `LocalAdapter` reads homebrew Markdown from disk. Adding another wiki is a configuration change. Adding a new kind of source means writing one class.

**HTTP client.** Each source gets a single shared `httpx.Client` with fixed timeouts and an identifying User-Agent. Requests go through a per-source throttle and a tenacity retry policy that reads `Retry-After` and backs off exponentially on 429, 5xx and `maxlag` responses. The client won't start unless a contact address is configured.

**Raw store.** Every response is written to `raw_payload` before any parsing, keyed by source, external ID and revision. PostgreSQL compresses large payloads automatically (TOAST), so keeping full response history is cheap. Because parsing reads only from this table, a parser fix can be applied to the whole corpus with no network traffic.

**Parsers.** These are pure functions from a raw payload to records, which makes them easy to test against saved fixtures. The wiki parser removes boilerplate, extracts and normalizes the infobox, splits the article into passages along its heading hierarchy, and resolves footnote markers to structured references. Rules that differ between sites (selectors, sections to drop, infobox classes) are declared per site, so they don't need to be hard-coded.

**Loader.** Validated records are upserted with SQLAlchemy. Each document is written in its own transaction: the document row, its passages, references and aliases are replaced together, so a reader never sees a half-updated article.

**Query services.** The search service builds weighted full-text queries with trigram fallback. The retrieval service runs full-text and vector queries in parallel, fuses their rankings, and hands the winning passages to a local model with strict grounding instructions.

### Ingestion pipeline

A run of `frlore ingest` moves each source through these stages:

1. **Discover.** List the members of each seed category (recursing to `max_depth`), follow continuation tokens, skip categories already visited, and collect seed pages along with any links they expand to. MediaWiki redirects are resolved and recorded as aliases.
2. **Check revisions.** Fetch the current revision ID for each discovered page in batches. Pages whose revision is already in the raw store are skipped.
3. **Fetch.** Retrieve rendered HTML, the revision ID, categories and section metadata through `action=parse`, then write the raw payload.
4. **Parse.** Clean the HTML, extract the infobox, segment the text into passages, and parse the footnotes.
5. **Classify and tag.** Assign a document type (deity, subrace, location, event, …) from the infobox template and categories. Map each reference to an edition using the rules in `config/sourcebooks.yaml`, and tag each passage with the editions cited inside it.
6. **Validate.** Build a `DocumentRecord` for each page. Records that fail validation are written to the run report with the validation error and are never loaded.
7. **Load.** Upsert the document and its children in one transaction. Search vectors are rebuilt for the affected passages.
8. **Link.** Group documents from different sources that describe the same subject into a shared *entity*. Matching uses normalized titles and aliases, plus curated overrides from `config/entity_links.yaml`.
9. **Embed** *(optional; `frlore embed`)*. Generate embeddings for passages whose text hash has no embedding under the configured model yet.

Every page is processed independently. A failure is logged against the run and doesn't stop the others, and re-running the command picks up where the last run left off. Runs are idempotent: ingesting the same revisions twice leaves the database unchanged.

---

## Data model

```mermaid
erDiagram
    SOURCE ||--o{ INGEST_RUN : "audited by"
    SOURCE ||--o{ RAW_PAYLOAD : "fetched into"
    SOURCE ||--o{ DOCUMENT : provides
    RAW_PAYLOAD ||--o{ DOCUMENT : "parsed into"
    DOCUMENT ||--o{ PASSAGE : "segmented into"
    DOCUMENT ||--o{ REFERENCE : cites
    DOCUMENT ||--o{ DOCUMENT_ALIAS : "also known as"
    PASSAGE ||--o{ PASSAGE_EMBEDDING : "embedded as"
    ENTITY ||--o{ ENTITY_DOCUMENT : groups
    DOCUMENT ||--o{ ENTITY_DOCUMENT : "linked by"
```

| Table | Purpose | Notable columns |
|-------|---------|-----------------|
| `source` | Registered sources and their licensing | `key`, `kind`, `base_url`, `license`, `license_url`, `exportable` |
| `ingest_run` | Audit trail for every ingestion run | `started_at`, `finished_at`, `discovered`, `fetched`, `skipped`, `rejected`, `status` |
| `raw_payload` | Unmodified API responses | `external_id`, `revision_id`, `content_type`, `payload`, `fetched_at` |
| `document` | One article or API entity | `title`, `url`, `doc_type`, `infobox` (JSONB), `categories`, `editions`, `revision_id`, `license`, `retrieved_at` |
| `document_alias` | Alternate names | `alias`, `origin` (redirect, infobox or curated) |
| `reference` | Parsed footnote citations | `citation_text`, `sourcebook`, `year`, `page`, `edition` |
| `passage` | The unit of search and retrieval | `ordinal`, `heading_path`, `text`, `editions`, `content_hash`, `search_vector` |
| `passage_embedding` | One vector per passage per model | `model`, `embedding` (vector), `content_hash`, `created_at` |
| `entity` | A subject that may be described by several sources | `name`, `entity_type` |
| `entity_document` | Links between entities and documents | `link_origin` (automatic or curated) |

**Integrity rules**
- A document is unique on `(source_id, external_id)`, which is what makes the loader's upserts idempotent.
- A raw payload is unique on `(source_id, external_id, revision_id)`, so each revision is stored exactly once.
- A passage embedding is unique on `(passage_id, model)`. Its `content_hash` shows when text has changed and needs a new embedding.

**Indexes**
- GIN on `passage.search_vector` for full-text search.
- GIN trigram (`gin_trgm_ops`) on `document.title` and `document_alias.alias` for fuzzy matching.
- GIN (`jsonb_path_ops`) on `document.infobox` for containment queries such as "deities whose portfolio includes magic".
- HNSW (`vector_cosine_ops`) on `passage_embedding.embedding` for nearest-neighbor search.

Every schema object, including extensions and the text-search configuration, is created and changed through Alembic migrations.

---

## Search

### Text-search configuration

Setting names are full of diacritics and irregular forms, so the index uses its own text-search configuration. Each word passes through three dictionaries in order:

```sql
CREATE TEXT SEARCH DICTIONARY frlore_synonyms (
    TEMPLATE = synonym,
    SYNONYMS = frlore            -- db/tsearch_data/frlore.syn, mounted into the container
);

CREATE TEXT SEARCH CONFIGURATION frlore (COPY = english);
ALTER TEXT SEARCH CONFIGURATION frlore
    ALTER MAPPING FOR hword, hword_part, word
    WITH unaccent, frlore_synonyms, english_stem;
```

1. **`unaccent`** folds diacritics, so *Faerûn*, *Faerun* and *faerun* all match.
2. **`frlore_synonyms`** maps forms a stemmer can't relate to their root. The Snowball English stemmer reduces *elves* to *elv*, so it never matches *elf*; the synonym file maps *elves* and *elven* (and *dwarves* and *dwarven*) to their singular root.
3. **`english_stem`** handles regular inflection, such as *deities* and *deity*.

The two-argument form of `to_tsvector` (with an explicit configuration) is immutable, so passage search vectors can be stored and indexed under this configuration.

### Ranking

Each passage's search vector is weighted by where the text comes from:

| Weight | Content |
|--------|---------|
| **A** | Document title and aliases |
| **B** | Heading path and infobox values |
| **C** | Passage body |

Results are ranked with `ts_rank_cd`, and exact title or alias matches get an extra boost. Queries are parsed with `websearch_to_tsquery`, which supports quoted phrases, `or` and `-term` exclusion. Snippets come from `ts_headline`.

### Fuzzy fallback

If a query looks like a name, or full-text search returns few results, the service also compares the query against titles and aliases by trigram similarity. A close match is offered as a suggestion (*corelon* → *Corellon Larethian*) or merged into the results.

### Filters

Searches can be narrowed by document type (`--type deity`), source (`--source wikipedia`) and edition (`--edition 2e`). The edition filter uses the passage-level tags derived from footnotes, so it selects text supported by sources from that edition.

---

## Question answering

`frlore ask` answers natural-language questions using only indexed material.

1. **Retrieve.** The question runs as a full-text query and as a vector query, each returning a ranked candidate list (40 passages by default). Any filters (`--edition`, `--source`, `--type`) apply to both.
2. **Fuse.** The two rankings are combined with reciprocal rank fusion. This rewards passages that both methods agree on and keeps exact-name matches that embeddings alone tend to miss.
3. **Ground.** The top passages (8 by default) are numbered and passed to the local chat model with instructions to answer only from those passages, cite every claim by number, report disagreements between sources or editions, and say so plainly when the passages don't contain the answer.
4. **Cite.** Each citation number in the answer is resolved to the passage's document, heading path, URL, revision ID and license.

Embeddings are stored per passage and per model, keyed by a hash of the passage text. Refreshing the corpus re-embeds only passages whose text actually changed, and switching to a different embedding model never mixes vectors from two models.

The question-answering layer is optional. Ingestion and search work fully without Ollama installed.

---

## Getting started

### Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose v2
- [Ollama](https://ollama.com/) *(optional, for question answering)*

### Installation

```bash
git clone https://github.com/<your-username>/fr-lore-index.git
cd fr-lore-index

uv sync                          # create the virtual environment and install dependencies
cp .env.example .env             # then set FRLORE_CONTACT (required)

docker compose up -d db          # PostgreSQL 17 with pgvector, unaccent, pg_trgm and the synonym file
uv run alembic upgrade head      # create the schema, extensions and search configuration
```

### Build the index

```bash
uv run frlore ingest             # discover, fetch, parse, validate and load all enabled sources
uv run frlore stats              # documents and passages by source and type
uv run frlore search "moon elf"
```

The first run fetches every page in scope, so it takes longer than later runs. After that, use `frlore refresh` to fetch only pages that have changed.

### Enable question answering (optional)

```bash
ollama pull nomic-embed-text     # embedding model (768 dimensions)
ollama pull llama3.1:8b          # or any chat model available in Ollama

uv run frlore embed
uv run frlore ask "Who leads the Seldarine?"
```

---

## Configuration

### Environment variables

Settings are read from the environment or from `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `FRLORE_DATABASE_URL` | `postgresql+psycopg://frlore:frlore@localhost:5432/frlore` | SQLAlchemy connection URL |
| `FRLORE_CONTACT` | *(required)* | Email address or URL included in the User-Agent so site operators can reach you |
| `FRLORE_REQUEST_DELAY` | `1.0` | Minimum seconds between requests to the same source |
| `FRLORE_HTTP_TIMEOUT` | `30` | Request timeout, in seconds |
| `FRLORE_MAX_RETRIES` | `5` | Maximum retry attempts for retryable responses |
| `FRLORE_SOURCES_FILE` | `config/sources.yaml` | Source definitions |
| `FRLORE_OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `FRLORE_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `FRLORE_CHAT_MODEL` | `llama3.1:8b` | Chat model used by `frlore ask` |
| `FRLORE_CANDIDATES` | `40` | Candidates taken from each retriever before fusion |
| `FRLORE_TOP_K` | `8` | Passages passed to the chat model |
| `FRLORE_LOG_LEVEL` | `INFO` | Logging verbosity |

The Docker Compose service reads `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` from the same `.env` file.

### Sources

Sources are declared in `config/sources.yaml`. Each one records its access details, its license and what to collect.

```yaml
sources:
  - key: fr-wiki
    name: Forgotten Realms Wiki
    kind: mediawiki
    api_url: https://forgottenrealms.fandom.com/api.php
    license: CC BY-SA
    license_url: https://www.fandom.com/licensing
    seeds:
      categories: [Elves, Tel-quessir, High elves, Wood elves, Wild elves, Dark elves, Elven kingdoms]
      pages: [Seldarine, Dark Seldarine]
      expand_links: { depth: 1, doc_types: [deity] }   # collect pantheon members from the seed pages
      max_depth: 2
      include_characters: false
    enabled: true

  - key: wikipedia
    name: Wikipedia
    kind: mediawiki
    api_url: https://en.wikipedia.org/w/api.php
    license: CC BY-SA 4.0
    license_url: https://creativecommons.org/licenses/by-sa/4.0/
    seeds:
      pages:
        - Elf (Dungeons & Dragons)
        - Drow (Dungeons & Dragons)
        - Half-elf (Dungeons & Dragons)
        - Seldarine
        - Corellon Larethian
        - Lolth
        - Eladrin
    enabled: true

  - key: open5e-srd
    name: Open5e (System Reference Documents)
    kind: open5e
    api_url: https://api.open5e.com/v2/
    license: CC BY 4.0
    license_url: https://creativecommons.org/licenses/by/4.0/
    documents: [srd-2014, srd-2024]     # SRD 5.1 and SRD 5.2 only
    resources:
      species: { name__icontains: elf }
    enabled: true

  - key: homebrew
    name: Campaign homebrew
    kind: local
    path: ./homebrew
    license: private
    exportable: false
    enabled: true
```

Other MediaWiki sites, such as the wikis for other D&D settings, are added the same way. Each needs its own `api_url` and its own declared license.

### Edition mapping

`config/sourcebooks.yaml` maps cited works to editions. Rules that match a title are applied first. Rules based on publisher and publication year are used as a fallback.

```yaml
titles:
  - match: "The Complete Book of Elves"
    edition: 2e
  - match: "Cormanthyr: Empire of the Elves"
    edition: 2e
  - match: "Races of Faerûn"
    edition: 3e
  - match: "Forgotten Realms Campaign Guide"
    edition: 4e

fallback:
  - publisher: "TSR"
    years: [1989, 1999]
    edition: 2e
  - publisher: "Wizards of the Coast"
    years: [2008, 2013]
    edition: 4e
```

Edition codes are `1e`, `2e`, `3e`, `3.5e`, `4e`, `5e-2014` and `5e-2024`. References that match no rule stay untagged; the index doesn't guess.

---

## Usage

### Command reference

| Command | Description |
|---------|-------------|
| `frlore ingest [--source KEY]` | Run the full pipeline for one source or all enabled sources |
| `frlore fetch [--source KEY] [--limit N]` | Discover and fetch raw payloads only |
| `frlore process [--source KEY] [--rebuild]` | Parse, validate and load from the raw store; `--rebuild` reprocesses every stored payload with no network access |
| `frlore refresh [--source KEY]` | Check revisions, then fetch and reprocess only changed pages |
| `frlore link` | Rebuild cross-source entity links |
| `frlore embed [--model NAME]` | Embed passages that lack an embedding for the given model |
| `frlore search QUERY [--type] [--source] [--edition] [--limit] [--json]` | Ranked full-text search with fuzzy fallback |
| `frlore show TITLE_OR_ID` | Show a document's infobox, passages, references, aliases and linked documents |
| `frlore ask QUESTION [--edition] [--source] [--show-passages]` | Answer a question from indexed sources, with citations |
| `frlore stats` | Counts by source, document type and edition |
| `frlore runs [--limit N]` | Recent ingestion runs and their outcomes |
| `frlore attribution DOC_ID...` | Generate license-compliant attribution text for the given documents |
| `frlore eval [--k N]` | Run the retrieval evaluation suite |

### Examples

Search across all sources:

```bash
frlore search "sun elf high magic"
frlore search '"crown wars" -drow' --edition 2e
frlore search "corelon"                       # suggests Corellon Larethian
frlore search "Teu-Tel'Quessir"               # resolves the alias to Moon elf
```

Search results as JSON. The values below are illustrative:

```json
{
  "rank": 1,
  "title": "Elf (Dungeons & Dragons)",
  "heading_path": ["Forgotten Realms"],
  "doc_type": "topic",
  "source": "wikipedia",
  "url": "https://en.wikipedia.org/wiki/Elf_(Dungeons_%26_Dragons)",
  "revision_id": 1300000000,
  "license": "CC BY-SA 4.0",
  "editions": ["3e", "4e"],
  "snippet": "Sun elves are the primary practitioners of elven <b>High Magic</b>…",
  "score": 0.87
}
```

Ask a question:

```text
$ frlore ask "Who leads the Seldarine, and which deities belong to it?"

The Seldarine is the elven pantheon, led by Corellon Larethian [1][2]. Its
members usually include Aerdrie Faenya, Deep Sashelas, Erevan Ilesere,
Fenmarel Mestarine, Hanali Celanil, Labelas Enoreth, Rillifane Rallathil,
Sehanine Moonbow and Solonor Thelandira; other elven gods appear in some
campaign settings [1].

Sources
[1] Elf (Dungeons & Dragons) — Wikipedia (CC BY-SA 4.0)
    https://en.wikipedia.org/wiki/Elf_(Dungeons_%26_Dragons)
[2] Corellon Larethian — Forgotten Realms Wiki (CC BY-SA)
    https://forgottenrealms.fandom.com/wiki/Corellon_Larethian
```

Inspect a document and prepare attribution before sharing:

```bash
frlore show "Corellon Larethian"
frlore attribution 412 418 973 > ATTRIBUTION.md
```

---

## Extending the index

**Another people or region.** Add seed categories or pages to an existing source and run `frlore ingest`. The schema doesn't depend on any species, so no migration is needed. Dwarves, for example, become new rows in the existing tables.

**Another wiki.** Add a `mediawiki` source with its API URL and license. If the site's markup differs, declare a parser profile for it (selectors for the infobox, sections to drop, the footnote format).

**Homebrew material.** Put Markdown files in `homebrew/`. Optional YAML front matter sets the title, type, aliases and tags. Headings become passages, so homebrew is searchable and retrievable alongside canon while staying clearly labeled by source. Because the homebrew source is `exportable: false`, it's excluded from attribution and export output.

**A new kind of source.** Implement the adapter interface and register its `kind`:

```python
class SourceAdapter(Protocol):
    def discover(self) -> Iterable[SourceItem]: ...
    def fetch(self, item: SourceItem) -> RawPayload: ...
    def parse(self, raw: RawPayload) -> Iterable[DocumentRecord]: ...
```

Everything after `parse` (validation, loading, search, embedding and linking) is shared, so a new adapter gets all of it automatically.

---

## Testing & evaluation

```bash
uv run pytest                    # unit tests; no network or database required
uv run pytest -m integration     # requires the Compose database
uv run frlore eval --k 5         # retrieval quality report
```

- **Parser tests** run against saved responses in `tests/fixtures/`, covering each page type (deity, pantheon, subrace, realm, location, event, character) plus Open5e JSON. A change to a wiki's markup shows up as a failing test before any bad data is loaded.
- **HTTP tests** use `httpx.MockTransport` to simulate timeouts, 5xx errors, `maxlag` errors and 429 responses with `Retry-After`. They check that retry and backoff behave correctly with no real network calls.
- **Search behavior tests** check, against a disposable database, how the index handles diacritics, irregular plurals, apostrophes, hyphenated elven terms, alias resolution, misspellings and edition filters.
- **Integration tests** cover migration round-trips (upgrade and downgrade), idempotency (ingesting the same revisions twice leaves row counts unchanged), and rebuilding the corpus from the raw store with networking disabled.
- **Retrieval evaluation** uses `eval/questions.yaml`, which pairs lore questions with the passages that should answer them. `frlore eval` reports recall@k and mean reciprocal rank for full-text-only, vector-only and hybrid retrieval, so retrieval changes are measured instead of guessed at.

---

## Project structure

```text
fr-lore-index/
├── alembic/                    # Migration environment and versioned migrations
├── config/
│   ├── sources.yaml            # Source definitions, seeds and licenses
│   ├── sourcebooks.yaml        # Sourcebook → edition mapping
│   └── entity_links.yaml       # Curated cross-source links
├── db/
│   └── tsearch_data/
│       └── frlore.syn          # Search synonyms (elves → elf), mounted into PostgreSQL
├── eval/
│   └── questions.yaml          # Retrieval evaluation set
├── homebrew/                   # Private campaign material (git-ignored)
├── src/frlore/
│   ├── cli.py                  # Typer application
│   ├── settings.py             # pydantic-settings configuration
│   ├── http/                   # Client, throttling, retry policy
│   ├── sources/                # mediawiki.py, open5e.py, local.py
│   ├── parsing/                # Cleaning, infobox, passages, references, classification
│   ├── models/
│   │   ├── records.py          # Pydantic record schemas
│   │   └── orm.py              # SQLAlchemy models
│   ├── pipeline/               # discover, fetch, process, refresh, link
│   ├── search/                 # Full-text, fuzzy, filters
│   └── rag/                    # Embeddings, hybrid retrieval, answering, evaluation
├── tests/
│   ├── fixtures/               # Saved API responses (with ATTRIBUTION.md)
│   ├── unit/
│   └── integration/
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
├── .env.example
└── LICENSE
```

---

## Data sources & licensing

| Source | Content | Access | License |
|--------|---------|--------|---------|
| [Forgotten Realms Wiki](https://forgottenrealms.fandom.com) | In-world lore: deities, subraces, realms, history | MediaWiki Action API | CC BY-SA ([Fandom licensing](https://www.fandom.com/licensing)) |
| [Wikipedia](https://en.wikipedia.org/wiki/Elf_(Dungeons_%26_Dragons)) | Publication history and edition changes | MediaWiki Action API | CC BY-SA 4.0 |
| [Open5e](https://open5e.com/) (SRD 5.1 and SRD 5.2 only) | Species rules | Open5e v2 REST API | CC BY 4.0 |
| Other setting wikis *(optional)* | Cross-setting lore | MediaWiki Action API | As declared per source |
| Local homebrew | Campaign material | Filesystem | Private; never exported |

**Deliberately excluded:** paywalled platforms, sites whose terms prohibit automated access, unlicensed copies of published books, and forum content with no clear license.

### What this repository distributes

The repository contains source code, configuration and a small set of test fixtures. Indexed content lives only in your local database and is never committed. The test fixtures are excerpts of CC BY-SA pages and are distributed under that license, with attribution in `tests/fixtures/ATTRIBUTION.md`.

### Sharing results

Using the index privately needs nothing extra. If you share material produced from it, such as published notes, screenshots or generated answers, the source licenses apply:

- **CC BY-SA content** (the wikis): credit the title, source URL, authors (via the page history) and license; note any changes you made; and release adaptations under the same license. `frlore attribution` generates this text from each document's stored provenance.
- **SRD content** (Open5e): include the attribution statement required by the relevant SRD version, exactly as published on the [D&D Beyond SRD page](https://www.dndbeyond.com/srd).

*Dungeons & Dragons, Forgotten Realms and their associated names are trademarks of Wizards of the Coast LLC. This project is unofficial and is not affiliated with or endorsed by Wizards of the Coast.*

---

## Responsible access

The ingestion client is built to be a good citizen on community-run infrastructure:

- **Identifies itself.** Every request carries a descriptive User-Agent with the tool's name, its version and the operator's contact address. The client refuses to run without one, and it never presents a browser User-Agent.
- **Uses APIs only.** All wiki content comes through `api.php`; rendered article pages are never crawled.
- **Throttles requests.** Each source gets one request at a time, with a configurable minimum delay between requests, well under the [Wikimedia guidance](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits) of no more than three concurrent requests.
- **Backs off under load.** It sends `maxlag` on MediaWiki requests, honors `Retry-After` on 429 responses, and backs off exponentially with jitter on errors.
- **Avoids redundant work.** Revision checks are batched, unchanged pages are never downloaded again, and parser fixes are applied from the raw store instead of by re-fetching.

See [API:Etiquette](https://www.mediawiki.org/wiki/API:Etiquette) and the [Wikimedia User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy) for the policies this behavior follows.

---

## Known limitations

- **Coverage follows upstream categorization.** Pages are discovered through the wikis' own categories and links. A page that is miscategorized upstream may be missed or included by mistake.
- **Edition tags are inferred from citations.** A passage's edition tags come from the sourcebooks it cites. Uncited text has no tags, and a passage that cites several editions carries all of them.
- **The index doesn't judge canon.** Community wikis can contain errors, speculation or conflicting accounts. The index keeps every source's claims separate and attributed; it doesn't decide which one is correct.
- **Answers depend on retrieval.** The model may only use the passages it's given, but a local model can still misread or overstate them. Check important claims against the cited passages with `frlore show`.
- **Parsers depend on markup.** If a wiki changes its templates or HTML, the parser profile may need updating. The fixture tests are there to catch this early.
- **Embedding dimensions are fixed per column.** The vector column is sized for the configured embedding model (768 dimensions for `nomic-embed-text`). Switching to a model with a different size requires a migration and a full re-embed.

---

## Acknowledgements

- The editors of the [Forgotten Realms Wiki](https://forgottenrealms.fandom.com) and Wikipedia, whose decades of careful cataloging and citation make this index possible.
- The [Open5e](https://open5e.com/) project, for an open, well-documented API over the System Reference Documents.
- Wizards of the Coast, for releasing the System Reference Documents under Creative Commons.
- The maintainers of PostgreSQL, pgvector, SQLAlchemy, Alembic, httpx, Beautiful Soup, Pydantic and Ollama.

---

## License

The source code is released under the terms in [LICENSE](LICENSE). Content indexed by this tool remains under its original licenses, as described in [Data sources & licensing](#data-sources--licensing).
