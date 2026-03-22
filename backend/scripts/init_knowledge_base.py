"""
Script to initialise the ElasticGuard knowledge base.
Run once before starting the backend:
    python -m scripts.init_knowledge_base
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from knowledge.knowledge_base import init_knowledge_base
from core.config import settings


async def main():
    print("ElasticGuard — Initialising Knowledge Base")
    print("=" * 45)
    ok = await init_knowledge_base(
        persist_dir=settings.CHROMA_PERSIST_DIR,
        ollama_base=settings.OLLAMA_BASE_URL,
    )
    if ok:
        print("✅  Knowledge base ready")
    else:
        print("⚠️   Knowledge base init failed (RAG disabled — AI agents will still work without it)")

if __name__ == "__main__":
    asyncio.run(main())
