#!/usr/bin/env python3
"""
Test fonctionnel de scraping - Affiche le contenu markdown d'une URL.

Usage:
    python scripts/test_scrape.py [URL] [--save]

Exemple:
    python scripts/test_scrape.py https://www.concilio.com/chirurgie-plastique
    python scripts/test_scrape.py https://www.concilio.com/chirurgie-plastique --save
"""
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


def clean_markdown(content: str) -> str:
    """Nettoie le markdown (max 2 retours à la ligne)."""
    cleaned = content
    # Supprimer les espaces/tabs sur les lignes "vides"
    cleaned = re.sub(r"\n[ \t]+\n", "\n\n", cleaned)
    # Plusieurs passes pour gérer les cas imbriqués
    while "\n\n\n" in cleaned:
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def scrape_url(url: str, save: bool = False) -> None:
    """Scrape une URL et affiche le contenu markdown."""
    print(f"\n{'=' * 60}")
    print(f"🔍 Scraping: {url}")
    print(f"{'=' * 60}\n")

    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler = AsyncWebCrawler(config=browser_config)

    try:
        await crawler.start()

        run_config = CrawlerRunConfig(
            word_count_threshold=10,
            exclude_external_links=True,
            remove_overlay_elements=True,
            process_iframes=False,
        )

        result = await asyncio.wait_for(
            crawler.arun(url=url, config=run_config),
            timeout=30,
        )

        if result.success:
            markdown = clean_markdown(result.markdown or "")
            title = result.metadata.get("title", "N/A") if result.metadata else "N/A"

            print("✅ Scraping réussi!\n")
            print(f"📊 Statistiques:")
            print(f"   - Longueur du markdown: {len(markdown)} caractères")
            print(f"   - Titre: {title}")

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
                    f.write(f"> Longueur: {len(markdown)} caractères\n\n")
                    f.write("---\n\n")
                    f.write(markdown)

                print(f"\n💾 Sauvegardé: {filepath}")
            else:
                print(f"\n{'─' * 60}")
                print("📄 CONTENU MARKDOWN:")
                print(f"{'─' * 60}\n")
                print(markdown)
        else:
            print(f"❌ Échec du scraping: {result.error_message}")

    except asyncio.TimeoutError:
        print("❌ Timeout - La page a mis trop de temps à charger")
    except Exception as e:
        print(f"❌ Erreur: {e}")
    finally:
        await crawler.close()


def main():
    args = sys.argv[1:]
    save = "--save" in args
    args = [a for a in args if a != "--save"]
    url = args[0] if args else "https://www.concilio.com/chirurgie-plastique"
    asyncio.run(scrape_url(url, save=save))


if __name__ == "__main__":
    main()
