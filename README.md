# SEO Scraper Service

Micro-service FastAPI de scraping haute performance avec [Crawl4AI](https://github.com/unclecode/crawl4ai).

## Fonctionnalités

- Scraping ultra-rapide avec Crawl4AI et Playwright
- Pipeline de nettoyage Markdown configurable (DOM pruning, Trafilatura, LLM)
- Support PDF natif avec extraction de métadonnées
- API REST simple avec batch processing
- Dashboard d'audit intégré
- Configuration 100% typée avec Pydantic
- Prêt pour Docker

## Installation

### Prérequis

- Python 3.10+
- pip

### Installation rapide

```bash
git clone <repo-url>
cd Python.SEO.Scraper

# Installer les dépendances
make install-dev

# Copier la configuration
cp .env.example .env
```

## Configuration

Toute la configuration est typée avec **Pydantic BaseSettings** et chargée depuis `.env`.

### Serveur

| Variable    | Type    | Défaut    | Description                           |
|-------------|---------|-----------|---------------------------------------|
| `HOST`      | str     | `0.0.0.0` | Adresse d'écoute                      |
| `PORT`      | int     | `8001`    | Port d'écoute                         |
| `LOG_LEVEL` | Literal | `INFO`    | DEBUG, INFO, WARNING, ERROR, CRITICAL |

### Crawler

| Variable                  | Type | Défaut  | Description                        |
|---------------------------|------|---------|------------------------------------|
| `CRAWLER_HEADLESS`        | bool | `true`  | Mode headless Playwright           |
| `CRAWLER_VERBOSE`         | bool | `false` | Logs verbeux du crawler            |
| `DEFAULT_TIMEOUT`         | int  | `30000` | Timeout par défaut (ms)            |
| `WORD_COUNT_THRESHOLD`    | int  | `10`    | Seuil minimum de mots par bloc     |
| `EXCLUDE_EXTERNAL_LINKS`  | bool | `true`  | Exclure les liens externes         |
| `REMOVE_OVERLAY_ELEMENTS` | bool | `false` | Supprimer les overlays (voir note) |
| `PROCESS_IFRAMES`         | bool | `false` | Traiter les iframes                |

> **Note sur REMOVE_OVERLAY_ELEMENTS**: Cette option peut supprimer du contenu important stylisé en overlay (compteurs de stats, modals avec contenu). Laissez à `false` par défaut.

### Attente JavaScript (SPAs)

| Variable              | Type  | Défaut | Description                                          |
|-----------------------|-------|--------|------------------------------------------------------|
| `DELAY_BEFORE_RETURN` | float | `2.0`  | Délai (secondes) après chargement avant capture HTML |
| `WAIT_FOR_SELECTOR`   | str   | `""`   | Sélecteur CSS à attendre (ex: `.content-loaded`)     |

Ces options sont cruciales pour les SPAs avec contenu chargé dynamiquement (compteurs animés, lazy loading).

### Pipeline de nettoyage

| Variable                | Type | Défaut  | Description                                   |
|-------------------------|------|---------|-----------------------------------------------|
| `ENABLE_DOM_PRUNING`    | bool | `true`  | Étape 1: Supprimer nav, footer, scripts, ads  |
| `USE_TRAFILATURA`       | bool | `true`  | Étape 2: Extraction contenu principal         |
| `ENABLE_REGEX_CLEANING` | bool | `true`  | Étape 3: Nettoyage regex (newlines, doublons) |
| `ENABLE_LLM_SANITIZER`  | bool | `false` | Étape 4: Restructuration IA des titres        |
| `INCLUDE_IMAGES`        | bool | `true`  | Inclure les images dans le markdown           |

### Gemini API (LLM Sanitizer)

| Variable                       | Type  | Défaut             | Description                  |
|--------------------------------|-------|--------------------|------------------------------|
| `GEMINI_API_KEY`               | str   | `""`               | Clé API Google Gemini        |
| `GEMINI_MODEL`                 | str   | `gemini-2.0-flash` | Modèle à utiliser            |
| `GEMINI_TEMPERATURE`           | float | `0.2`              | Température de génération    |
| `GEMINI_MAX_TOKENS`            | int   | `8192`             | Tokens max en sortie         |
| `LLM_MAX_CONTENT_LOSS_PERCENT` | float | `10.0`             | Seuil de rejet si perte > X% |

### Autres

| Variable                  | Type      | Défaut            | Description                       |
|---------------------------|-----------|-------------------|-----------------------------------|
| `DATABASE_PATH`           | Path      | `data/scraper.db` | Chemin SQLite                     |
| `DASHBOARD_ENABLED`       | bool      | `true`            | Activer le dashboard `/dashboard` |
| `MAX_CONCURRENT_BROWSERS` | int       | `5`               | Limite de browsers parallèles     |
| `RETRY_MAX_ATTEMPTS`      | int       | `3`               | Tentatives max sur erreur réseau  |
| `CORS_ORIGINS`            | List[str] | `["*"]`           | Origins CORS autorisées           |

## Pipeline de traitement

Le contenu HTML passe par plusieurs étapes configurables:

| Étape | Nom             | Description                                                 |
|-------|-----------------|-------------------------------------------------------------|
| 1     | DOM Pruning     | BeautifulSoup supprime nav, footer, scripts, cookie banners |
| 2     | Trafilatura     | Extraction intelligente du contenu principal                |
| 3     | Title Injection | Ajout H1 si absent (depuis og:title ou URL)                 |
| 4     | Regex Cleaning  | Normalisation newlines, suppression doublons                |
| 5     | LLM Sanitizer   | Correction cascade H1 > H2 > H3 via Gemini                  |

Le pipeline inclut un **fallback intelligent**: si Trafilatura extrait moins de 30% du contenu Crawl4AI, le système utilise automatiquement le markdown Crawl4AI pour éviter la perte de données sur les pages marketing.

## Utilisation

### Lancement

```bash
make run-dev    # Mode développement (auto-reload)
make run        # Mode production
```

Service disponible sur `http://localhost:8001`

### API Endpoints

**GET /health** - État du service

```bash
curl http://localhost:8001/health
```

**POST /scrape** - Scraper une URL

```bash
curl -X POST http://localhost:8001/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "timeout": 30000}'
```

**POST /scrape/batch** - Scraper plusieurs URLs

```bash
curl -X POST http://localhost:8001/scrape/batch \
  -H "Content-Type: application/json" \
  -d '["https://example.com", "https://example.org"]'
```

### Script de test

```bash
# Afficher le markdown
make scrape URL=https://example.com

# Sauvegarder dans tests/samples/
make scrape-save URL=https://example.com
```

## Tests

```bash
make test          # Exécuter les tests (82 tests)
make test-cov      # Tests avec couverture
make lint          # Vérifier le code
make format        # Formater le code
```

## Docker

```bash
docker compose up -d        # Lancer
docker compose logs -f      # Logs
docker compose down         # Arrêter
```

## Debugging: cas réel

### Problème: statistiques manquantes

Sur `https://www.concilio.com`, les compteurs (25000 médecins, 5000 pathologies, etc.) n'apparaissaient pas dans le markdown final.

### Méthode de debug

1. **Vérifier le HTML brut**

```python
# Le HTML contient-il les données?
# noinspection PyUnresolvedReferences
print("25000" in crawl_result.html)  # True ✓
```

2. **Vérifier le markdown Crawl4AI**

```python
# Crawl4AI les extrait-il ?
# noinspection PyUnresolvedReferences
print("25000" in crawl_result.markdown)  # Dépend des options
```

3. **Isoler le coupable par élimination**

```python
# Tester chaque option séparément
for remove_overlay in [False, True]:
    # noinspection PyUnresolvedReferences
    run_config = CrawlerRunConfig(remove_overlay_elements=remove_overlay)
    # noinspection PyUnresolvedReferences
    result = crawler.arun(url, config=run_config)
    print(f"remove_overlay={remove_overlay}: {'25000' in result.markdown}")
```

4. **Résultat**

```
remove_overlay_elements=False: 16546 chars, 25000: True
remove_overlay_elements=True:  12435 chars, 25000: False  ← Coupable!
```

### Cause

L'option `remove_overlay_elements=True` de Crawl4AI identifiait la section des statistiques comme un "overlay" (probablement à cause du CSS/positionnement) et la supprimait.

### Solution

Changer la valeur par défaut de `REMOVE_OVERLAY_ELEMENTS` à `false` dans la configuration.

### Leçon

Quand du contenu disparaît dans le pipeline, isoler chaque étape avec des tests binaires (on/off) pour identifier rapidement le coupable.

## Structure du projet

```
src/seo_scraper/
├── api.py              # Endpoints FastAPI
├── config.py           # Configuration Pydantic (100% typée)
├── scraper.py          # Service de scraping avec retry
├── pipeline.py         # Pipeline de nettoyage markdown
├── gemini_client.py    # Client API Gemini async
├── pdf_scraper.py      # Extraction PDF
├── database.py         # SQLite pour logs
├── dashboard.py        # Dashboard d'audit
└── templates/
    └── prompts/
        └── sanitizer.j2  # Prompt Jinja2 pour LLM
```

## Licence

MIT
