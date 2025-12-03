#!/usr/bin/env python3
"""
Test fonctionnel de scraping - Affiche le contenu markdown d'une URL.

Utilise le ScraperService avec le ContentPipeline complet:
- DOM Pruning (suppression nav, footer, scripts, ads)
- Trafilatura (extraction contenu principal)
- Title Injection (ajout H1 si manquant)
- Regex Cleaning (normalisation whitespace)
- LLM Sanitizer (restructuration IA, si activé)

Usage:
    python scripts/test_scrape.py [URL] [--save]

Exemple:
    python scripts/test_scrape.py https://www.concilio.com/chirurgie-plastique
    python scripts/test_scrape.py https://www.concilio.com/chirurgie-plastique --save
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seo_scraper.scraper import scraper_service


async def scrape_url(url: str, save: bool = False) -> None:
    """Scrape une URL via ScraperService avec le pipeline complet."""
    print(f"\n{'=' * 60}")
    print(f"🔍 Scraping: {url}")
    print(f"{'=' * 60}\n")

    try:
        # Démarrer le service
        await scraper_service.start()

        # Scraper avec le pipeline complet
        result = await scraper_service.scrape(url, timeout=30000)

        if result.success:
            markdown = result.markdown
            title = result.extracted_title or "N/A"

            print("✅ Scraping réussi!\n")
            print(f"📊 Statistiques:")
            print(f"   - Longueur du markdown: {len(markdown)} caractères")
            print(f"   - Titre extrait: {title}")
            print(f"   - Type de contenu: {result.content_type}")
            print(f"   - Liens trouvés: {result.links_count}")
            print(f"   - Images trouvées: {result.images_count}")
            print(f"   - Durée: {result.duration_ms}ms")

            if result.pipeline_steps:
                print(f"   - Pipeline steps: {', '.join(result.pipeline_steps)}")

            if result.retry_count > 0:
                print(f"   - Retries: {result.retry_count}")

            if save:
                # Sauvegarde dans tests/samples/
                parsed = urlparse(url)
                # Nom de fichier basé sur domaine + path
                path_slug = parsed.path.strip("/").replace("/", "_") or "index"
                filename = f"{parsed.netloc}_{path_slug}.md"
                samples_dir = Path("tests/samples")
                samples_dir.mkdir(parents=True, exist_ok=True)
                filepath = samples_dir / filename

                with open(filepath, "w") as f:
                    f.write(f"# Scrape de {parsed.netloc}{parsed.path}\n\n")
                    f.write(f"> URL: {url}\n")
                    f.write(f"> Titre: {title}\n")
                    f.write(f"> Longueur: {len(markdown)} caractères\n")
                    f.write(f"> Type: {result.content_type}\n")
                    if result.pipeline_steps:
                        f.write(f"> Pipeline: {', '.join(result.pipeline_steps)}\n")
                    f.write("\n---\n\n")
                    f.write(markdown)

                print(f"\n💾 Sauvegardé: {filepath}")
            else:
                print(f"\n{'─' * 60}")
                print("📄 CONTENU MARKDOWN:")
                print(f"{'─' * 60}\n")
                print(markdown)
        else:
            print(f"❌ Échec du scraping: {result.error}")
            if result.http_status_code:
                print(f"   - HTTP Status: {result.http_status_code}")

    except asyncio.TimeoutError:
        print("❌ Timeout - La page a mis trop de temps à charger")
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper_service.stop()


def main():
    args = sys.argv[1:]
    save = "--save" in args
    args = [a for a in args if a != "--save"]
    url = args[0] if args else "https://www.concilio.com"
    asyncio.run(scrape_url(url, save=save))


if __name__ == "__main__":
    main()
