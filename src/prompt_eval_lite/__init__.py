"""prompt-eval-lite: a small regression test runner for LLM prompts."""

from .baseline import Comparison, compare, load_report
from .expectations import check
from .loader import LoadError, load_suite
from .models import Expectation, RunResult, Suite, TestCase, TestResult
from .providers import (
    MockProvider,
    OllamaProvider,
    OpenAICompatProvider,
    Provider,
    ProviderError,
    make_provider,
)
from .runner import run_suite

__version__ = "0.1.0"

__all__ = [
    "Comparison",
    "Expectation",
    "LoadError",
    "MockProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "ProviderError",
    "RunResult",
    "Suite",
    "TestCase",
    "TestResult",
    "__version__",
    "check",
    "compare",
    "load_report",
    "load_suite",
    "make_provider",
    "run_suite",
]
