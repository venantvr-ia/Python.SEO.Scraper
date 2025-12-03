# -*- coding: utf-8 -*-
"""
Centralized Jinja2 environment for prompt templates.

Provides automatic cleanup of excessive whitespace and standard configuration.
"""
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template

from .config import settings


class CleanTemplate(Template):
    """Template that automatically cleans excessive blank lines."""

    _EXCESS_NEWLINES = re.compile(r"\n{3,}")

    def render(self, *args, **kwargs) -> str:
        """Render template and clean excessive newlines."""
        output = super().render(*args, **kwargs)
        return self._EXCESS_NEWLINES.sub("\n\n", output).strip()


def create_jinja_env(template_dir: Path | str | None = None) -> Environment:
    """
    Create a configured Jinja2 environment.

    Args:
        template_dir: Path to templates directory. Defaults to settings.PROMPTS_DIR.

    Returns:
        Configured Jinja2 Environment instance.
    """
    if template_dir is None:
        template_dir = settings.PROMPTS_DIR

    template_dir = Path(template_dir)

    # Create directory if it doesn't exist
    template_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
        autoescape=False,  # No HTML escaping for prompts
    )

    # Use our custom template class
    env.template_class = CleanTemplate

    return env


# Default environment instance
_default_env: Environment | None = None


def get_jinja_env() -> Environment:
    """Get or create the default Jinja2 environment."""
    global _default_env
    if _default_env is None:
        _default_env = create_jinja_env()
    return _default_env


def render_prompt(template_name: str, **context) -> str:
    """
    Render a prompt template with the given context.

    Args:
        template_name: Name of the template file (e.g., "sanitizer.j2")
        **context: Variables to pass to the template

    Returns:
        Rendered prompt string
    """
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)
