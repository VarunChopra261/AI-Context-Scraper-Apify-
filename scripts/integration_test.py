import asyncio
import logging
import os
import sys

# Configure logging to output to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", filename="integration_test.log", filemode="w")
logger = logging.getLogger(__name__)

# Add src to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.orchestrator import ContextOrchestrator

async def run_tests():
    # Load environment variables if they exist
    github_token = os.getenv("GITHUB_TOKEN")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if not github_token:
        logger.warning("No GITHUB_TOKEN provided. GitHub code search testing might skip.")

    orchestrator = ContextOrchestrator(
        logger=logger,
        github_token=github_token,
        enable_cache=False,  # Force a fresh run without caching
        enable_stackoverflow=True,
        chunk_size=500,
        enable_llm_synthesis=bool(openrouter_key),
        openrouter_api_key=openrouter_key,
        openrouter_model="arcee-ai/trinity-large-preview:free",
    )

    test_cases = [
        "Write an async Rust webhook handler using Axum that validates ed25519 signatures from an external payload",
        "Setup a real-time multiplayer WebSocket synchronizer using FastAPI and Redis PubSub with connection draining logic",
        "Build a multi-agent system using LangGraph with cyclical graphs and conditional edges that interact over a shared state",
    ]

    for idx, test_case in enumerate(test_cases, 1):
        logger.info(f"--- Running Test Case {idx}: {test_case} ---")
        try:
            result = await orchestrator.run(
                task=test_case,
                max_sources=5,
                allowed_domains=[],
                include_github=True,
                include_github_code_search=True,
                github_code_languages=["rust", "python"],
                max_code_snippets=5,
                include_stackoverflow=True,
            )
            
            metrics = result.get("metrics", {})
            sources = metrics.get('counts', {}).get('sources_found', metrics.get('sources_discovered', 0))
            scraped = metrics.get('counts', {}).get('pages_scraped', 0)
            
            if "errors" in result.get("open_questions", [])[0:1]: # Catching gracefully handled errors
                logger.error(f"Test case {idx} encountered pipeline failure: {result.get('open_questions')}")
            else:
                logger.info(f"Test case {idx} successful. Sources discovered: {sources}, Pages scraped: {scraped}")
                
            if sources == 0:
                logger.warning(f"Test case {idx} found 0 sources!")
                
        except Exception as e:
            logger.exception(f"Test case {idx} failed with unhandled exception: {e}")

if __name__ == "__main__":
    asyncio.run(run_tests())
