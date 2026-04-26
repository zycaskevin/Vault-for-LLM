"""Vault-for-LLM — Local-first knowledge system for LLM agents."""

__version__ = "0.4.0"

from .guardrails_db import GuardrailsDB
from .guardrails_search import GuardrailsSearch
from .guardrails_compile import GuardrailsCompiler
from .guardrails_embed import create_embedding_provider, EmbeddingProvider
from .guardrails_llm import create_llm_provider, LLMProvider
from .guardrails_graph import GuardrailsGraph
from .guardrails_log import log, setup_logging