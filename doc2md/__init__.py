"""
doc2md-cli
Universal Document to LLM-Optimized Markdown Converter
"""

__version__ = "0.1.0"
__author__ = "Zephyrus Labs"
__maintainer__ = "Shubham Sharma"
__email__ = "zephyrus.labs@gmail.com"
__developer_email__ = "sharmashubham25962@gmail.com"

from .core import convert_to_markdown, DocumentResult

__all__ = [
    "convert_to_markdown",
    "DocumentResult",
    "__version__",
    "__author__",
    "__maintainer__",
    "__email__",
    "__developer_email__",
]
