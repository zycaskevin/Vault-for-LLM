"""Vault-for-LLM — Local-first knowledge system for LLM agents."""

__version__ = "0.6.23"

from .db import VaultDB as VaultDB
from .search import VaultSearch as VaultSearch
from .compiler import VaultCompiler as VaultCompiler
from .embed import (
    create_embedding_provider as create_embedding_provider,
    EmbeddingProvider as EmbeddingProvider,
)
from .llm import create_llm_provider as create_llm_provider, LLMProvider as LLMProvider
from .graph import VaultGraph as VaultGraph
from .log import log as log, setup_logging as setup_logging
