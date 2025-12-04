# -*- coding: utf-8 -*-
"""
Tests for scientific article extraction (ScienceDirect, etc.).

These tests verify that abstracts, keywords, and full content are properly
extracted from scientific publisher HTML, which Trafilatura would otherwise strip.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from seo_scraper.pipeline import ContentPipeline

# Path to test samples
SAMPLES_DIR = Path(__file__).parent / "samples"


class TestScientificDomainDetection:
    """Tests for scientific domain detection."""

    def test_detects_sciencedirect(self):
        """Should detect sciencedirect.com as scientific."""
        pipeline = ContentPipeline()
        assert pipeline._is_scientific_site("https://www.sciencedirect.com/article/123")

    def test_detects_springer(self):
        """Should detect springer.com as scientific."""
        pipeline = ContentPipeline()
        assert pipeline._is_scientific_site("https://link.springer.com/article/123")

    def test_detects_nature(self):
        """Should detect nature.com as scientific."""
        pipeline = ContentPipeline()
        assert pipeline._is_scientific_site("https://www.nature.com/articles/123")

    def test_detects_pubmed(self):
        """Should detect pubmed as scientific."""
        pipeline = ContentPipeline()
        assert pipeline._is_scientific_site("https://pubmed.ncbi.nlm.nih.gov/123")

    def test_non_scientific_site(self):
        """Should not detect regular sites as scientific."""
        pipeline = ContentPipeline()
        assert not pipeline._is_scientific_site("https://example.com/article")
        assert not pipeline._is_scientific_site("https://blog.example.org/post")


class TestScientificPreprocessing:
    """Tests for scientific content preprocessing."""

    def test_extracts_abstract_with_heading(self):
        """Should extract abstract with its heading."""
        pipeline = ContentPipeline()
        html = """
        <div class="abstract author">
            <h2>Résumé</h2>
            <div class="abstract-content">
                <p>Ceci est le contenu du résumé qui doit être extrait correctement.</p>
            </div>
        </div>
        """
        _, extracted = pipeline._step_scientific_preprocess(html)

        assert "## Résumé" in extracted
        assert "contenu du résumé" in extracted

    def test_extracts_multiple_abstracts(self):
        """Should extract both French and English abstracts."""
        pipeline = ContentPipeline()
        html = """
        <div class="abstracts">
            <div class="abstract author" id="abs1">
                <h2>Résumé</h2>
                <div class="abstract-content">
                    <p>Le résumé en français avec suffisamment de contenu pour passer le seuil.</p>
                </div>
            </div>
            <div class="abstract author" id="abs2">
                <h2>Summary</h2>
                <div class="abstract-content">
                    <p>The English summary with enough content to pass the threshold check.</p>
                </div>
            </div>
        </div>
        """
        _, extracted = pipeline._step_scientific_preprocess(html)

        assert "## Résumé" in extracted
        assert "résumé en français" in extracted
        assert "## Summary" in extracted
        assert "English summary" in extracted

    def test_extracts_keywords(self):
        """Should extract keywords section."""
        pipeline = ContentPipeline()
        html = """
        <div class="keywords">
            <h2>Mots clés</h2>
            <span class="keyword">Papillomavirus</span>
            <span class="keyword">Vaccination</span>
            <span class="keyword">Cancer</span>
        </div>
        """
        _, extracted = pipeline._step_scientific_preprocess(html)

        assert "## Mots clés" in extracted
        assert "Papillomavirus" in extracted
        assert "Vaccination" in extracted
        assert "Cancer" in extracted


@pytest.mark.asyncio
class TestScienceDirectRealHTML:
    """
    Integration tests using real ScienceDirect HTML sample.

    These tests verify that the pipeline correctly extracts content from
    actual ScienceDirect article HTML, based on the original issue:
    - Abstracts (Résumé/Summary) were completely missing
    - Keywords sections were empty
    - Content was truncated before reference links [1]
    - Content order was wrong

    Note: These tests explicitly disable the LLM sanitizer to test the
    traditional scientific extraction pipeline.
    """

    @pytest.fixture(autouse=True)
    def disable_llm_sanitizer(self):
        """Disable LLM sanitizer for these tests to test traditional extraction."""
        with patch("seo_scraper.pipeline.settings") as mock_settings:
            mock_settings.ENABLE_LLM_HTML_SANITIZER = False
            mock_settings.ENABLE_LLM_STRUCTURE_SANITIZER = False
            mock_settings.GEMINI_API_KEY = ""
            mock_settings.ENABLE_DOM_PRUNING = True
            mock_settings.USE_TRAFILATURA = True
            mock_settings.ENABLE_REGEX_CLEANING = True
            mock_settings.INCLUDE_IMAGES = True
            mock_settings.LLM_MAX_CONTENT_LOSS_PERCENT = 10.0
            yield

    @pytest.fixture
    def sciencedirect_html(self) -> str:
        """Load the ScienceDirect sample HTML."""
        html_path = SAMPLES_DIR / "sciencedirect.01.html"
        if not html_path.exists():
            pytest.skip(f"Sample file not found: {html_path}")
        return html_path.read_text(encoding="utf-8")

    @pytest.fixture
    def pipeline(self) -> ContentPipeline:
        """Create a pipeline instance."""
        return ContentPipeline()

    async def test_extracts_french_abstract(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : Le résumé français (Résumé) doit être présent.

        L'abstract en français ne doit pas être supprimé par Trafilatura.
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        assert "Résumé" in result.markdown, "Le résumé français est manquant"
        assert "scientific_preprocess" in result.steps_applied

    async def test_extracts_english_abstract(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : Le résumé anglais (Summary) doit être présent.

        L'abstract en anglais ne doit pas être supprimé par Trafilatura.
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        assert "Summary" in result.markdown, "Le résumé anglais est manquant"

    async def test_extracts_keywords_content(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : Les mots clés doivent avoir du contenu, pas juste le header.

        La section keywords ne doit pas être vide (juste "## Mots clés").
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        # Vérifier que "Mots clés" est suivi de contenu
        markdown = result.markdown
        if "Mots clés" in markdown:
            # Trouver la position de "Mots clés" et vérifier qu'il y a du contenu après
            idx = markdown.find("Mots clés")
            section_after = markdown[idx:idx + 200]
            # Il doit y avoir plus que juste le header
            lines = section_after.split("\n")
            content_lines = [line for line in lines[1:] if line.strip()]
            assert len(content_lines) > 0, "La section Mots clés est vide"

    async def test_abstracts_have_substantial_content(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : Les résumés extraits doivent avoir du contenu substantiel.

        Le contenu des abstracts ne doit pas être vide ou tronqué.
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        markdown = result.markdown

        # Le résumé français doit avoir du contenu (plus de 100 chars après le header)
        if "## Résumé" in markdown:
            idx = markdown.find("## Résumé")
            next_section = markdown.find("##", idx + 10)
            if next_section == -1:
                next_section = len(markdown)
            resume_content = markdown[idx + 10:next_section].strip()
            assert len(resume_content) > 100, "Le résumé français est trop court"

    async def test_has_minimum_content(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : Le contenu extrait doit inclure au moins les abstracts.

        Avec abstracts français et anglais + mots clés, on attend au moins 1500 chars.
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        # Abstracts + keywords should be at least 1500 characters
        assert len(result.markdown) > 1500, (
            f"Contenu trop court ({len(result.markdown)} chars), "
            "l'extraction des abstracts a probablement échoué"
        )

    async def test_scientific_inject_step_applied(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : L'étape scientific_inject doit être appliquée.

        Cela confirme que les abstracts extraits ont été réinjectés.
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        assert "scientific_preprocess" in result.steps_applied
        # Si du contenu scientifique a été extrait, scientific_inject doit aussi être là
        if "Résumé" in result.markdown or "Summary" in result.markdown:
            assert "scientific_inject" in result.steps_applied

    async def test_extracts_body_content(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : Le corps de l'article (Introduction, etc.) doit être extrait.

        La phrase "La prise en charge diagnostique et thérapeutique sera discutée"
        doit être présente dans le markdown nettoyé.
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        # Vérifier la présence de la phrase spécifique demandée
        assert "La prise en charge diagnostique et thérapeutique sera discutée" in result.markdown, (
            "La phrase du corps de l'article est manquante"
        )

        # Vérifier que les sections principales sont présentes
        assert "Introduction" in result.markdown, "La section Introduction est manquante"

    async def test_extracts_multiple_body_sections(self, pipeline, sciencedirect_html):
        """
        CRITÈRE : Plusieurs sections du corps doivent être extraites.

        L'article contient Introduction, Tendinopathies, Syndromes, etc.
        """
        result = await pipeline.process(
            html=sciencedirect_html,
            url="https://www.sciencedirect.com/science/article/pii/S1169833025001875",
            crawl4ai_markdown="",
        )

        sections_to_check = ["Introduction", "Tendinopathies", "Conclusion"]
        found_sections = [s for s in sections_to_check if s in result.markdown]

        assert len(found_sections) >= 2, (
            f"Seulement {len(found_sections)} sections trouvées sur {len(sections_to_check)}: {found_sections}"
        )
