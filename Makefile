.PHONY: help venv install install-dev clean run run-dev test test-cov lint format check-format clean-all scrape scrape-save check status docker-build docker-run docker-stop docker-logs dashboard db-reset db-backup

PYTHON := python3.11
VENV := .venv
BIN := $(VENV)/bin
PORT := 8001
HOST := 0.0.0.0
DATA_DIR := data

# =============================================================================
# HELP
# =============================================================================

help:
	@echo "SEO Scraper Service v2.0 - Commandes disponibles:"
	@echo ""
	@echo "  make install       - Créer le venv et installer les dépendances"
	@echo "  make install-dev   - Installation avec outils de développement"
	@echo "  make run           - Lancer le service en mode production"
	@echo "  make run-dev       - Lancer le service en mode développement (reload)"
	@echo "  make test          - Exécuter les tests"
	@echo "  make test-cov      - Exécuter les tests avec couverture"
	@echo "  make lint          - Vérifier le code avec ruff"
	@echo "  make format        - Formatter le code avec black"
	@echo "  make check-format  - Vérifier le formatage sans modifier"
	@echo "  make clean         - Nettoyer les fichiers temporaires"
	@echo "  make clean-all     - Nettoyer tout (venv, cache, etc.)"
	@echo "  make scrape        - Test de scraping (URL=... optionnel)"
	@echo "  make scrape-save   - Scrape et sauvegarde dans tests/samples/"
	@echo "  make check         - Vérifier l'état du service"
	@echo "  make status        - Afficher le statut du service"
	@echo ""
	@echo "Dashboard & Base de données:"
	@echo "  make dashboard     - Ouvrir le dashboard dans le navigateur"
	@echo "  make db-reset      - Réinitialiser la base de données"
	@echo "  make db-backup     - Sauvegarder la base de données"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  - Construire l'image Docker"
	@echo "  make docker-run    - Lancer le conteneur"
	@echo "  make docker-stop   - Arrêter le conteneur"
	@echo "  make docker-logs   - Voir les logs du conteneur"
	@echo ""

# =============================================================================
# INSTALLATION
# =============================================================================

venv:
	@echo "Création de l'environnement virtuel..."
	$(PYTHON) -m venv $(VENV)
	@echo "✓ Environnement virtuel créé"
	@echo "  Activez-le avec: source $(VENV)/bin/activate"

install: venv
	@echo "Installation des dépendances..."
	$(BIN)/pip install --upgrade pip setuptools wheel
	$(BIN)/pip install -e .
	@echo "Installation de Playwright pour Crawl4AI..."
	$(BIN)/crawl4ai-setup
	@echo "✓ Installation terminée"

install-dev: venv
	@echo "Installation des dépendances de développement..."
	$(BIN)/pip install --upgrade pip setuptools wheel
	$(BIN)/pip install -e ".[dev]"
	@echo "Installation de Playwright pour Crawl4AI..."
	$(BIN)/crawl4ai-setup
	@echo "✓ Installation dev terminée"

# =============================================================================
# LANCEMENT
# =============================================================================

run:
	@echo "Lancement du service (production)..."
	@echo "URL: http://$(HOST):$(PORT)"
	@echo "Docs: http://$(HOST):$(PORT)/docs"
	$(BIN)/seo-scraper

run-dev:
	@echo "Lancement du service (développement avec reload)..."
	@echo "URL: http://$(HOST):$(PORT)"
	@echo "Docs: http://$(HOST):$(PORT)/docs"
	HOST=$(HOST) PORT=$(PORT) $(BIN)/uvicorn seo_scraper.api:app --host $(HOST) --port $(PORT) --reload

# =============================================================================
# TESTS
# =============================================================================

test:
	@echo "Exécution des tests..."
	$(BIN)/pytest

test-cov:
	@echo "Exécution des tests avec couverture..."
	$(BIN)/pytest --cov=seo_scraper --cov-report=html --cov-report=term

# =============================================================================
# QUALITÉ DU CODE
# =============================================================================

lint:
	@echo "Vérification du code avec ruff..."
	$(BIN)/ruff check src/ tests/

format:
	@echo "Formatage du code avec black..."
	$(BIN)/black src/ tests/

check-format:
	@echo "Vérification du formatage..."
	$(BIN)/black --check src/ tests/

# =============================================================================
# NETTOYAGE
# =============================================================================

clean:
	@echo "Nettoyage des fichiers temporaires..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	rm -rf .pytest_cache
	rm -rf .coverage htmlcov
	rm -rf dist build *.egg-info
	@echo "✓ Nettoyage terminé"

clean-all: clean
	@echo "Suppression complète (y compris venv)..."
	rm -rf $(VENV)
	rm -rf .playwright
	@echo "✓ Nettoyage complet terminé"

# =============================================================================
# UTILITAIRES
# =============================================================================

scrape:
	@echo "Test de scraping fonctionnel..."
	@if [ -z "$(URL)" ]; then \
		$(BIN)/python scripts/test_scrape.py https://www.concilio.com; \
	else \
		$(BIN)/python scripts/test_scrape.py $(URL); \
	fi

scrape-save:
	@echo "Scraping et sauvegarde dans tests/samples/..."
	@if [ -z "$(URL)" ]; then \
		$(BIN)/python scripts/test_scrape.py https://www.concilio.com --save; \
	else \
		$(BIN)/python scripts/test_scrape.py $(URL) --save; \
	fi

check:
	@echo "Vérification de l'état du service..."
	@curl -s http://localhost:$(PORT)/health > /dev/null 2>&1 && echo "✓ Service OK" || (echo "✗ Service non accessible" && exit 1)

status:
	@curl -s http://localhost:$(PORT)/health | python3 -m json.tool || echo "Service non accessible"

# =============================================================================
# DOCKER
# =============================================================================

docker-build:
	@echo "Construction de l'image Docker..."
	docker build -t seo-scraper:latest .

docker-run:
	@echo "Lancement du conteneur..."
	docker compose up -d
	@echo "Service disponible sur http://localhost:$(PORT)"

docker-stop:
	@echo "Arrêt du conteneur..."
	docker compose down

docker-logs:
	docker compose logs -f

# =============================================================================
# DASHBOARD & BASE DE DONNÉES
# =============================================================================

dashboard:
	@echo "Ouverture du dashboard..."
	@xdg-open http://localhost:$(PORT)/dashboard/ 2>/dev/null || open http://localhost:$(PORT)/dashboard/ 2>/dev/null || echo "Ouvrez http://localhost:$(PORT)/dashboard/ dans votre navigateur"

db-reset:
	@echo "Réinitialisation de la base de données..."
	@rm -f $(DATA_DIR)/scraper.db
	@echo "✓ Base de données supprimée (sera recréée au prochain démarrage)"

db-backup:
	@echo "Sauvegarde de la base de données..."
	@mkdir -p backups
	@cp $(DATA_DIR)/scraper.db backups/scraper_$$(date +%Y%m%d_%H%M%S).db 2>/dev/null && echo "✓ Backup créé dans backups/" || echo "✗ Pas de base de données à sauvegarder"
