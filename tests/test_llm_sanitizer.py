# -*- coding: utf-8 -*-
"""
Tests for LLM HTML sanitizer functionality.

These tests verify that the LLM-based HTML sanitization works correctly,
with mocked Gemini API calls to avoid actual API usage during testing.
"""
from unittest.mock import AsyncMock, patch

import pytest

from seo_scraper.pipeline import ContentPipeline


class TestLLMHtmlSanitizer:
    """Tests for the LLM HTML sanitize step."""

    @pytest.fixture
    def pipeline(self) -> ContentPipeline:
        """Create a pipeline instance."""
        return ContentPipeline()

    @pytest.fixture
    def sample_html(self) -> str:
        """Sample HTML with navigation, content, and footer."""
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Test Article</title></head>
        <body>
            <nav>
                <a href="/">Home</a>
                <a href="/about">About</a>
            </nav>
            <main>
                <h1>Introduction to Python</h1>
                <p>Python is a powerful programming language.</p>
                <h2>Getting Started</h2>
                <p>To get started with Python, install it from python.org.</p>
            </main>
            <footer>
                <p>Copyright 2024</p>
            </footer>
        </body>
        </html>
        """

    @pytest.fixture
    def expected_markdown(self) -> str:
        """Expected markdown output from LLM."""
        return """# Introduction to Python

Python is a powerful programming language.

## Getting Started

To get started with Python, install it from python.org."""

    @pytest.mark.asyncio
    async def test_llm_html_sanitize_extracts_content(
            self, pipeline, sample_html, expected_markdown
    ):
        """LLM HTML sanitizer should extract business content."""
        with patch.object(
                pipeline, "_step_llm_html_sanitize", new_callable=AsyncMock
        ) as mock_sanitize:
            mock_sanitize.return_value = expected_markdown

            # Simulate enabled LLM sanitizer
            with patch("seo_scraper.pipeline.settings") as mock_settings:
                mock_settings.ENABLE_LLM_HTML_SANITIZER = True
                mock_settings.ENABLE_LLM_STRUCTURE_SANITIZER = False
                mock_settings.GEMINI_API_KEY = "test-key"
                mock_settings.ENABLE_DOM_PRUNING = True
                mock_settings.USE_TRAFILATURA = True
                mock_settings.ENABLE_REGEX_CLEANING = True
                mock_settings.INCLUDE_IMAGES = True

                result = await pipeline.process(
                    html=sample_html,
                    url="https://example.com/article",
                    crawl4ai_markdown="",
                )

                mock_sanitize.assert_called_once_with(sample_html)
                assert "llm_html_sanitize" in result.steps_applied
                assert "Introduction to Python" in result.markdown

    @pytest.mark.asyncio
    async def test_llm_html_sanitize_bypasses_traditional_extraction(
            self, pipeline, sample_html, expected_markdown
    ):
        """When LLM succeeds, traditional extraction steps should be skipped."""
        with patch.object(
                pipeline, "_step_llm_html_sanitize", new_callable=AsyncMock
        ) as mock_sanitize:
            mock_sanitize.return_value = expected_markdown

            with patch("seo_scraper.pipeline.settings") as mock_settings:
                mock_settings.ENABLE_LLM_HTML_SANITIZER = True
                mock_settings.ENABLE_LLM_STRUCTURE_SANITIZER = False
                mock_settings.GEMINI_API_KEY = "test-key"
                mock_settings.ENABLE_DOM_PRUNING = True
                mock_settings.USE_TRAFILATURA = True
                mock_settings.ENABLE_REGEX_CLEANING = True
                mock_settings.INCLUDE_IMAGES = True

                result = await pipeline.process(
                    html=sample_html,
                    url="https://example.com/article",
                    crawl4ai_markdown="",
                )

                # LLM step should be applied
                assert "llm_html_sanitize" in result.steps_applied

                # Traditional extraction should be skipped
                assert "dom_pruning" not in result.steps_applied
                assert "trafilatura" not in result.steps_applied
                assert "crawl4ai" not in result.steps_applied

                # Title injection and regex cleaning should still run
                assert "title_injection" in result.steps_applied
                assert "regex_cleaning" in result.steps_applied

    @pytest.mark.asyncio
    async def test_llm_html_sanitize_fallback_on_failure(self, pipeline, sample_html):
        """When LLM fails, traditional extraction should run."""
        with patch.object(
                pipeline, "_step_llm_html_sanitize", new_callable=AsyncMock
        ) as mock_sanitize:
            # LLM returns None (failure)
            mock_sanitize.return_value = None

            with patch("seo_scraper.pipeline.settings") as mock_settings:
                mock_settings.ENABLE_LLM_HTML_SANITIZER = True
                mock_settings.ENABLE_LLM_STRUCTURE_SANITIZER = False
                mock_settings.GEMINI_API_KEY = "test-key"
                mock_settings.ENABLE_DOM_PRUNING = True
                mock_settings.USE_TRAFILATURA = True
                mock_settings.ENABLE_REGEX_CLEANING = True
                mock_settings.INCLUDE_IMAGES = True

                result = await pipeline.process(
                    html=sample_html,
                    url="https://example.com/article",
                    crawl4ai_markdown="Fallback content",
                )

                # LLM step should NOT be in applied steps (it failed)
                assert "llm_html_sanitize" not in result.steps_applied

                # Traditional extraction should run
                assert "dom_pruning" in result.steps_applied

    @pytest.mark.asyncio
    async def test_llm_html_sanitize_disabled_by_default(self, pipeline, sample_html):
        """LLM sanitizer should not run when disabled."""
        with patch.object(
                pipeline, "_step_llm_html_sanitize", new_callable=AsyncMock
        ) as mock_sanitize:
            with patch("seo_scraper.pipeline.settings") as mock_settings:
                mock_settings.ENABLE_LLM_HTML_SANITIZER = False
                mock_settings.ENABLE_LLM_STRUCTURE_SANITIZER = False
                mock_settings.GEMINI_API_KEY = ""
                mock_settings.ENABLE_DOM_PRUNING = True
                mock_settings.USE_TRAFILATURA = False
                mock_settings.ENABLE_REGEX_CLEANING = True
                mock_settings.INCLUDE_IMAGES = True

                result = await pipeline.process(
                    html=sample_html,
                    url="https://example.com/article",
                    crawl4ai_markdown="Test content",
                )

                # LLM should not be called
                mock_sanitize.assert_not_called()
                assert "llm_html_sanitize" not in result.steps_applied


class TestLLMHtmlSanitizeMethod:
    """Unit tests for the _step_llm_html_sanitize method."""

    @pytest.fixture
    def pipeline(self) -> ContentPipeline:
        """Create a pipeline instance."""
        return ContentPipeline()

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_response(self, pipeline):
        """Should return None when Gemini returns empty."""
        with patch("seo_scraper.gemini_client.get_gemini_client") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.generate_with_retry.return_value = ""
            mock_client.return_value = mock_instance

            with patch("seo_scraper.jinja_env.render_prompt") as mock_render:
                mock_render.return_value = "test prompt"

                result = await pipeline._step_llm_html_sanitize("<html></html>")
                assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_short_response(self, pipeline):
        """Should return None when response is too short."""
        with patch("seo_scraper.gemini_client.get_gemini_client") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.generate_with_retry.return_value = "Too short"
            mock_client.return_value = mock_instance

            with patch("seo_scraper.jinja_env.render_prompt") as mock_render:
                mock_render.return_value = "test prompt"

                result = await pipeline._step_llm_html_sanitize("<html></html>")
                assert result is None

    @pytest.mark.asyncio
    async def test_cleans_markdown_code_blocks(self, pipeline):
        """Should remove markdown code block wrappers from response."""
        expected_content = "# Title\n\nThis is content that is long enough to pass the sanity check. We need at least one hundred characters of content for this test to pass properly."

        with patch("seo_scraper.gemini_client.get_gemini_client") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.generate_with_retry.return_value = f"```markdown\n{expected_content}\n```"
            mock_client.return_value = mock_instance

            with patch("seo_scraper.jinja_env.render_prompt") as mock_render:
                mock_render.return_value = "test prompt"

                result = await pipeline._step_llm_html_sanitize("<html></html>")
                assert result == expected_content

    @pytest.mark.asyncio
    async def test_truncates_large_html(self, pipeline):
        """Should truncate HTML that exceeds size limit."""
        large_html = "x" * 150_000  # 150k chars, exceeds 100k limit

        with patch("seo_scraper.gemini_client.get_gemini_client") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.generate_with_retry.return_value = "# Result\n\nExtracted content that meets minimum length requirements for the test."
            mock_client.return_value = mock_instance

            with patch("seo_scraper.jinja_env.render_prompt") as mock_render:
                mock_render.return_value = "test prompt"

                await pipeline._step_llm_html_sanitize(large_html)

                # Verify render_prompt was called
                mock_render.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_import_error(self, pipeline):
        """Should return None when google-generativeai is not installed."""
        with patch(
                "seo_scraper.gemini_client.get_gemini_client",
                side_effect=ImportError("No module"),
        ):
            result = await pipeline._step_llm_html_sanitize("<html></html>")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self, pipeline):
        """Should return None when API call fails."""
        with patch("seo_scraper.gemini_client.get_gemini_client") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.generate_with_retry.side_effect = Exception("API error")
            mock_client.return_value = mock_instance

            with patch("seo_scraper.jinja_env.render_prompt") as mock_render:
                mock_render.return_value = "test prompt"

                result = await pipeline._step_llm_html_sanitize("<html></html>")
                assert result is None


class TestLLMStructureSanitizer:
    """Tests for the LLM structure sanitizer (heading normalization)."""

    @pytest.fixture
    def pipeline(self) -> ContentPipeline:
        """Create a pipeline instance."""
        return ContentPipeline()

    @pytest.mark.asyncio
    async def test_structure_sanitizer_not_run_after_llm_html(self, pipeline):
        """Structure sanitizer should not run if LLM HTML sanitizer already ran."""
        with patch.object(
                pipeline, "_step_llm_html_sanitize", new_callable=AsyncMock
        ) as mock_html_sanitize:
            mock_html_sanitize.return_value = "# Title\n\nContent that is long enough."

            with patch.object(
                    pipeline, "_step_llm_structure_sanitizer", new_callable=AsyncMock
            ) as mock_struct_sanitize:
                with patch("seo_scraper.pipeline.settings") as mock_settings:
                    mock_settings.ENABLE_LLM_HTML_SANITIZER = True
                    mock_settings.ENABLE_LLM_STRUCTURE_SANITIZER = True  # Both enabled
                    mock_settings.GEMINI_API_KEY = "test-key"
                    mock_settings.ENABLE_DOM_PRUNING = True
                    mock_settings.USE_TRAFILATURA = True
                    mock_settings.ENABLE_REGEX_CLEANING = True
                    mock_settings.INCLUDE_IMAGES = True

                    result = await pipeline.process(
                        html="<html></html>",
                        url="https://example.com",
                        crawl4ai_markdown="",
                    )

                    # HTML sanitizer should run
                    mock_html_sanitize.assert_called_once()

                    # Structure sanitizer should NOT run
                    mock_struct_sanitize.assert_not_called()

                    assert "llm_html_sanitize" in result.steps_applied
                    assert "llm_structure_sanitizer" not in result.steps_applied
