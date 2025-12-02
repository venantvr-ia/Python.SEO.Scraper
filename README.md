# SEO Scraper Service

Micro-service FastAPI de scraping haute performance avec [Crawl4AI](https://github.com/unclecode/crawl4ai).

## 📋 Fonctionnalités

- 🚀 Scraping ultra-rapide avec Crawl4AI et Playwright
- 🎯 API REST simple et intuitive
- 📝 Export en Markdown nettoyé
- ⚡ Support du scraping parallèle (batch)
- 🔒 Gestion robuste des erreurs et timeouts
- 📊 Health check intégré
- 🐳 Prêt pour Docker
- 📚 Documentation Swagger automatique

## 🏗️ Structure du projet

```
Python.SEO.Scraper/
├── src/
│   └── seo_scraper/
│       ├── __init__.py       # Exports publics
│       ├── __main__.py       # Point d'entrée CLI
│       ├── api.py            # Endpoints FastAPI
│       ├── config.py         # Configuration centralisée
│       ├── models.py         # Modèles Pydantic
│       └── scraper.py        # Service de scraping
├── tests/
│   ├── samples/              # Fichiers MD de test
│   ├── __init__.py
│   ├── conftest.py           # Configuration pytest
│   ├── test_api.py           # Tests API
│   └── test_models.py        # Tests modèles
├── scripts/
│   └── test_scrape.py        # Script de test fonctionnel
├── Dockerfile                # Image Docker
├── docker-compose.yml        # Orchestration Docker
├── .dockerignore
├── .env.example              # Exemple de configuration
├── pyproject.toml            # Configuration du projet
├── Makefile                  # Commandes de développement
└── README.md
```

## 🚀 Installation

### Prérequis

- Python 3.10+
- pip

### Installation rapide

```bash
# Cloner le dépôt
git clone <repo-url>
cd Python.SEO.Scraper

# Installer les dépendances
make install

# Ou pour le développement
make install-dev
```

### Configuration

Copier le fichier d'exemple et l'adapter si nécessaire :

```bash
cp .env.example .env
```

Variables d'environnement disponibles :

| Variable           | Défaut    | Description                                 |
|--------------------|-----------|---------------------------------------------|
| `HOST`             | `0.0.0.0` | Adresse d'écoute du serveur                 |
| `PORT`             | `8001`    | Port d'écoute                               |
| `LOG_LEVEL`        | `INFO`    | Niveau de log (DEBUG, INFO, WARNING, ERROR) |
| `CRAWLER_HEADLESS` | `true`    | Mode headless pour le navigateur            |
| `DEFAULT_TIMEOUT`  | `30000`   | Timeout par défaut (ms)                     |

## 🎯 Utilisation

### Lancement du service

```bash
# Mode production
make run

# Mode développement (avec auto-reload)
make run-dev

# Ou directement avec le CLI installé
seo-scraper
```

Le service démarre sur `http://localhost:8001`

Documentation interactive : `http://localhost:8001/docs`

### API Endpoints

#### `GET /health`

Vérifie l'état du service.

```bash
curl http://localhost:8001/health
```

Réponse :

```json
{
  "status": "healthy",
  "crawler_ready": true,
  "version": "1.0.0"
}
```

#### `POST /scrape`

Scrape une URL et retourne le contenu en Markdown.

```bash
curl -X POST http://localhost:8001/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "timeout": 30000
  }'
```

**Request:**

```json
{
  "url": "https://example.com",
  "ignore_body_visibility": true,
  "timeout": 30000
}
```

**Response:**

```json
{
  "url": "https://example.com",
  "success": true,
  "markdown": "# Example Domain\n\nThis domain is for use...",
  "content_length": 1234,
  "error": null
}
```

#### `POST /scrape/batch`

Scrape plusieurs URLs en parallèle.

```bash
curl -X POST http://localhost:8001/scrape/batch \
  -H "Content-Type: application/json" \
  -d '["https://example.com", "https://example.org"]'
```

**Response:** Array de `ScrapeResponse`

### Utilisation en Python

```python
import httpx

# Client pour le service
client = httpx.Client(base_url="http://localhost:8001")

# Scraper une URL
response = client.post("/scrape", json={
    "url": "https://example.com",
    "timeout": 60000
})
data = response.json()

if data["success"]:
    print(f"Contenu: {data['markdown'][:100]}...")
else:
    print(f"Erreur: {data['error']}")
```

## 🧪 Tests

```bash
# Exécuter tous les tests
make test

# Tests avec couverture
make test-cov

# Rapport HTML de couverture généré dans htmlcov/
```

## 🛠️ Développement

### Commandes disponibles

```bash
# Installation
make install           # Installation production
make install-dev       # Installation développement

# Lancement
make run               # Lancer en production
make run-dev           # Lancer en mode dev (auto-reload)

# Tests & Qualité
make test              # Exécuter les tests
make test-cov          # Tests avec couverture
make lint              # Vérifier le code (ruff)
make format            # Formater le code (black)
make check-format      # Vérifier le formatage

# Scraping
make scrape            # Test de scraping (URL=... optionnel)
make scrape-save       # Scrape et sauvegarde dans tests/samples/

# Utilitaires
make clean             # Nettoyer les fichiers temp
make clean-all         # Nettoyage complet (+ venv)
make check             # Vérifier si le service tourne
make status            # Afficher le statut détaillé

# Docker
make docker-build      # Construire l'image Docker
make docker-run        # Lancer avec docker compose
make docker-stop       # Arrêter le conteneur
make docker-logs       # Voir les logs
```

### Qualité du code

Le projet utilise :

- **black** pour le formatage
- **ruff** pour le linting
- **pytest** pour les tests

```bash
# Formatter automatiquement
make format

# Vérifier sans modifier
make lint
make check-format
```

## 🐳 Docker

### Avec Docker Compose (recommandé)

```bash
# Construire et lancer
docker compose up -d

# Voir les logs
docker compose logs -f

# Arrêter
docker compose down
```

### Avec Docker directement

```bash
# Construire l'image
docker build -t seo-scraper .

# Lancer le conteneur
docker run -d \
  --name seo-scraper \
  -p 8001:8001 \
  -e LOG_LEVEL=INFO \
  -e DEFAULT_TIMEOUT=30000 \
  seo-scraper

# Vérifier le statut
docker logs seo-scraper
curl http://localhost:8001/health
```

### Configuration Docker

Variables d'environnement disponibles :

```yaml
environment:
  - HOST=0.0.0.0
  - PORT=8001
  - LOG_LEVEL=INFO
  - CRAWLER_HEADLESS=true
  - DEFAULT_TIMEOUT=30000
```

### Health Check

Le conteneur inclut un health check automatique qui vérifie `/health` toutes les 30 secondes.

## 🔗 Intégration avec Python.SEO.Gemini

Ce micro-service est conçu pour être utilisé avec Python.SEO.Gemini :

```python
# Dans le .env de Python.SEO.Gemini
SCRAPER_SERVICE_URL = "http://localhost:8001"
SCRAPER_TIMEOUT = 60
```

## 📝 Licence

MIT

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une PR.

## 📞 Support

Pour toute question ou problème, ouvrez une issue sur GitHub.
