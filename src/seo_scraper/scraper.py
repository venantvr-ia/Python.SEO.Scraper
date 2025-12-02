# -*- coding: utf-8 -*-
"""
Service de scraping utilisant Crawl4AI.
"""
import asyncio
import logging
import re

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from .config import config

logger = logging.getLogger(__name__)


class ScraperService:
    """Service de scraping avec gestion du cycle de vie du crawler."""

    def __init__(self):
        self.crawler: AsyncWebCrawler | None = None
        self._browser_config = BrowserConfig(
            headless=config.CRAWLER_HEADLESS,
            verbose=config.CRAWLER_VERBOSE,
        )

    async def start(self):
        """Initialise et démarre le crawler."""
        logger.info("Initialisation du crawler Crawl4AI...")
        self.crawler = AsyncWebCrawler(config=self._browser_config)
        await self.crawler.start()
        logger.info("Crawler prêt")

    async def stop(self):
        """Arrête le crawler proprement."""
        logger.info("Fermeture du crawler...")
        if self.crawler:
            await self.crawler.close()
            self.crawler = None
        logger.info("Crawler fermé")

    @property
    def is_ready(self) -> bool:
        """Vérifie si le crawler est prêt."""
        return self.crawler is not None

    async def scrape(
        self,
        url: str,
        timeout: int = config.DEFAULT_TIMEOUT,
    ) -> tuple[bool, str, str | None]:
        """
        Scrape une URL et retourne le contenu en Markdown.

        Args:
            url: URL à scraper
            timeout: Timeout en millisecondes

        Returns:
            Tuple (success, markdown_content, error_message)
        """
        if not self.crawler:
            return False, "", "Crawler non initialisé"

        logger.info(f"Scraping: {url[:80]}...")

        try:
            # Configuration du crawl
            run_config = CrawlerRunConfig(
                word_count_threshold=config.WORD_COUNT_THRESHOLD,
                exclude_external_links=config.EXCLUDE_EXTERNAL_LINKS,
                remove_overlay_elements=config.REMOVE_OVERLAY_ELEMENTS,
                process_iframes=config.PROCESS_IFRAMES,
            )

            # Exécuter le crawl avec timeout
            result = await asyncio.wait_for(
                self.crawler.arun(url=url, config=run_config),
                timeout=timeout / 1000,  # Convertir en secondes
            )

            if not result.success:
                error_msg = result.error_message or "Échec du scraping"
                logger.warning(f"Échec scraping: {url[:60]} - {error_msg}")
                return False, "", error_msg

            # Extraire et nettoyer le markdown
            markdown_content = result.markdown or ""
            markdown_content = self._clean_markdown(markdown_content)

            logger.info(f"Succès: {url[:60]} ({len(markdown_content)} chars)")
            return True, markdown_content, None

        except asyncio.TimeoutError:
            error_msg = f"Timeout après {timeout}ms"
            logger.error(f"Timeout: {url[:60]}")
            return False, "", error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erreur scraping {url[:60]}: {e}")
            return False, "", error_msg

    @staticmethod
    def _clean_markdown(content: str) -> str:
        """Nettoie le contenu markdown (limite à 2 retours à la ligne max)."""
        cleaned = content
        # Supprimer les espaces/tabs sur les lignes "vides"
        cleaned = re.sub(r"\n[ \t]+\n", "\n\n", cleaned)
        # Plusieurs passes pour gérer les cas imbriqués
        while "\n\n\n" in cleaned:
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


# Instance globale du service
scraper_service = ScraperService()
