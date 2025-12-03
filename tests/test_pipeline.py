# -*- coding: utf-8 -*-
"""
Tests for the content processing pipeline.
"""
import pytest

from seo_scraper.pipeline import ContentPipeline, PipelineResult


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        result = PipelineResult(markdown="# Test")

        assert result.markdown == "# Test"
        assert result.title is None
        assert result.steps_applied == []
        assert result.metadata == {}


class TestContentPipeline:
    """Tests for ContentPipeline."""

    def test_dom_pruning_removes_nav(self):
        """Should remove nav elements."""
        pipeline = ContentPipeline()
        html = "<html><body><nav>Menu</nav><main>Content</main></body></html>"

        result = pipeline._step_pruning(html)

        assert "<nav>" not in result
        assert "Content" in result

    def test_dom_pruning_removes_footer(self):
        """Should remove footer elements."""
        pipeline = ContentPipeline()
        html = "<html><body><main>Content</main><footer>Footer</footer></body></html>"

        result = pipeline._step_pruning(html)

        assert "<footer>" not in result
        assert "Content" in result

    def test_dom_pruning_removes_scripts(self):
        """Should remove script elements."""
        pipeline = ContentPipeline()
        html = "<html><body><script>alert('x')</script><p>Content</p></body></html>"

        result = pipeline._step_pruning(html)

        assert "<script>" not in result
        assert "alert" not in result
        assert "Content" in result

    def test_dom_pruning_removes_cookie_classes(self):
        """Should remove elements with cookie-related classes."""
        pipeline = ContentPipeline()
        html = '<html><body><div class="cookie-banner">Accept</div><p>Content</p></body></html>'

        result = pipeline._step_pruning(html)

        assert "cookie-banner" not in result
        assert "Accept" not in result
        assert "Content" in result

    def test_title_injection_preserves_existing_h1(self):
        """Should not modify content if H1 already exists."""
        pipeline = ContentPipeline()
        markdown = "# Existing Title\n\nContent here."

        result, title = pipeline._step_title_injection(
            markdown, "Page Title", "OG Title", "https://example.com/page"
        )

        assert result.startswith("# Existing Title")
        assert title == "Existing Title"

    def test_title_injection_adds_h1_from_og_title(self):
        """Should inject H1 from og:title if missing."""
        pipeline = ContentPipeline()
        markdown = "Content without title."

        result, title = pipeline._step_title_injection(
            markdown, "Page Title", "OG Title", "https://example.com/page"
        )

        assert result.startswith("# OG Title\n")
        assert title == "OG Title"
        assert "Content without title." in result

    def test_title_injection_adds_h1_from_page_title(self):
        """Should inject H1 from page title if og:title missing."""
        pipeline = ContentPipeline()
        markdown = "Content without title."

        result, title = pipeline._step_title_injection(
            markdown, "Page Title", None, "https://example.com/page"
        )

        assert result.startswith("# Page Title\n")
        assert title == "Page Title"

    def test_title_injection_uses_url_slug_fallback(self):
        """Should extract title from URL slug if no metadata."""
        pipeline = ContentPipeline()
        markdown = "Content without title."

        result, title = pipeline._step_title_injection(
            markdown, None, None, "https://example.com/my-awesome-page.html"
        )

        assert result.startswith("# My Awesome Page\n")
        assert title == "My Awesome Page"

    def test_regex_cleaning_removes_empty_links(self):
        """Should remove empty markdown links."""
        pipeline = ContentPipeline()
        markdown = "Text [](https://example.com) more text."

        result = pipeline._step_regex_cleaning(markdown)

        assert "[](https://example.com)" not in result
        assert "Text" in result
        assert "more text" in result

    def test_regex_cleaning_normalizes_newlines(self):
        """Should limit consecutive newlines to 2."""
        pipeline = ContentPipeline()
        markdown = "Line 1\n\n\n\n\nLine 2"

        result = pipeline._step_regex_cleaning(markdown)

        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_regex_cleaning_removes_empty_images(self):
        """Should remove images without src."""
        pipeline = ContentPipeline()
        markdown = "Text ![alt]() more text."

        result = pipeline._step_regex_cleaning(markdown)

        assert "![alt]()" not in result

    def test_regex_cleaning_removes_broken_image_artifacts(self):
        """Should remove ! ! broken image artifacts."""
        pipeline = ContentPipeline()
        markdown = "Text ! ! more text."

        result = pipeline._step_regex_cleaning(markdown)

        assert "! !" not in result

    def test_regex_cleaning_removes_video_player_noise(self):
        """Should remove video player artifacts."""
        pipeline = ContentPipeline()
        markdown = "Content\n0:00\n/\nLIVE\n-0:00\nMore content"

        result = pipeline._step_regex_cleaning(markdown)

        assert "0:00" not in result
        assert "LIVE" not in result
        assert "Content" in result
        assert "More content" in result

    def test_regex_cleaning_removes_duplicate_blocks(self):
        """Should remove duplicate consecutive blocks."""
        pipeline = ContentPipeline()
        markdown = "Block A\nLine 2\n\nBlock A\nLine 2\n\nBlock B"

        result = pipeline._step_regex_cleaning(markdown)

        # Should only have one "Block A" section
        assert result.count("Block A") == 1
        assert "Block B" in result

    def test_extract_text_content(self):
        """Should extract plain text from markdown."""
        text = ContentPipeline._extract_text_content(
            "# Title\n\n[Link](https://example.com)\n\n**Bold** text"
        )

        assert "Title" in text
        assert "Link" in text
        assert "Bold" in text
        assert "https://example.com" not in text
        assert "**" not in text


@pytest.mark.asyncio
class TestContentPipelineAsync:
    """Async tests for ContentPipeline."""

    async def test_process_with_html(self):
        """Should process HTML through pipeline."""
        pipeline = ContentPipeline()
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <nav>Menu</nav>
            <main>
                <h1>Main Title</h1>
                <p>This is the main content.</p>
            </main>
            <footer>Footer</footer>
        </body>
        </html>
        """

        result = await pipeline.process(
            html=html,
            url="https://example.com/test",
            crawl4ai_markdown="# Fallback\n\nFallback content.",
            page_title="Test Page",
        )

        assert result.markdown
        assert len(result.steps_applied) > 0
        assert "dom_pruning" in result.steps_applied

    async def test_process_fallback_to_crawl4ai(self):
        """Should fallback to Crawl4AI markdown if trafilatura fails."""
        pipeline = ContentPipeline()
        html = ""  # Empty HTML will make trafilatura fail

        result = await pipeline.process(
            html=html,
            url="https://example.com/test",
            crawl4ai_markdown="# Crawl4AI Content\n\nFrom crawler.",
            page_title="Test Page",
        )

        assert "Crawl4AI Content" in result.markdown or "From crawler" in result.markdown
