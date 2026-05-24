"""Vault-for-LLM — Local-first knowledge system for LLM agents."""

__version__ = "0.4.3"

from .db import VaultDB
from .search import VaultSearch
from .compiler import VaultCompiler
from .embed import create_embedding_provider, EmbeddingProvider
from .llm import create_llm_provider, LLMProvider
from .graph import VaultGraph
from .log import log, setup_logging