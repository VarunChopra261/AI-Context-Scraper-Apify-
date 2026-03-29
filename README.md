# AI Context Scraper - Production-Grade Developer Knowledge Engine

## Overview

A world-class Apify Actor that intelligently compiles high-quality coding context for AI agents, developer copilots, and engineering RAG systems. Transforms any coding task into structured, LLM-optimized context with documentation, code examples, implementation patterns, and best practices.

## 🚀 Key Features

### Multi-Source Knowledge Mining
- **Web Search**: DuckDuckGo integration with documentation prioritization
- **GitHub Intelligence**: Repository and code search with star-based ranking
- **StackOverflow Q&A**: High-quality accepted answers from developer community
- **Documentation Priority**: Boosted ranking for official docs (Python, AWS, FastAPI, etc.)

### LLM RAG Synthesis
- **Actionable Guidance**: Synthesizes gathered context into actionable insights using OpenRouter (`arcee-ai/trinity-large-preview:free` or custom models)
- **Automatic Prompting**: Builds token-optimized context prompts with code snippets, patterns, and SO answers
- **Graceful Degradation**: If the LLM call fails or times out, the pipeline safely falls back to returning the raw structured context

### Advanced Intelligence
- **Semantic Relevance Filtering**: Sentence-transformers embeddings for precision ranking
- **Implementation Pattern Detection**: Automatically identifies auth, caching, async, database patterns
- **Content Deduplication**: MinHash/shingling-based near-duplicate removal
- **Code Quality Scoring**: Ranks snippets by completeness, relevance, and documentation

### Enterprise Features
- **Caching Layer**: Apify KV store for pages, embeddings, and results (configurable TTL)
- **Observability Suite**: Comprehensive metrics (timing, counts, quality scores, cache stats)
- **Configurable Pipeline**: Tunable chunk size, source limits, spam filtering
- **Production-Ready**: Async architecture, retry logic, rate limiting, graceful degradation

## 📊 Output Structure

```json
{
  "task": "Build a FastAPI endpoint for S3 uploads",
  "context": {
    "concepts": [
      {
        "title": "FastAPI File Uploads",
        "summary": "FastAPI supports file uploads using UploadFile...",
        "source": "https://fastapi.tiangolo.com/tutorial/request-files"
      }
    ],
    "code_snippets": [
      {
        "language": "python",
        "description": "FastAPI S3 upload implementation",
        "code": "from fastapi import FastAPI, UploadFile\nimport boto3...",
        "source": "https://github.com/..."
      }
    ],
    "api_references": [
      {
        "library": "boto3",
        "function": "s3.upload_fileobj",
        "description": "Usage pattern with arguments: (file, bucket, key)",
        "source": "..."
      }
    ],
    "best_practices": [
      {
        "practice": "Use async endpoints in FastAPI for I/O operations",
        "reason": "Extracted from authoritative guidance text.",
        "source": "..."
      }
    ],
    "implementation_patterns": [
      {
        "pattern_type": "async_concurrency",
        "description": "Asynchronous and concurrent execution pattern",
        "code_snippet": "async def upload(file: UploadFile)...",
        "source": "...",
        "confidence": 0.95
      }
    ],
    "stackoverflow_answers": [
      {
        "question_title": "How to upload files to S3 with FastAPI?",
        "question_url": "https://stackoverflow.com/questions/...",
        "answer_body": "You can use boto3.client('s3').upload_fileobj()...",
        "score": 128,
        "accepted": true,
        "tags": ["python", "fastapi", "aws-s3"]
      }
    ],
    "llm_chunks": [
      {
        "text": "FastAPI provides the UploadFile class...",
        "tokens": 487,
        "source": "..."
      }
    ]
  },
  "llm_guidance": {
    "content": "## Overview\nFastAPI provides robust file upload capabilities...",
    "model": "arcee-ai/trinity-large-preview:free",
    "tokens_used": 1229,
    "finish_reason": "stop"
  },
  "metrics": {
    "timing": {
      "total_seconds": 12.34,
      "search_seconds": 2.1,
      "crawl_seconds": 6.5,
      "extraction_seconds": 2.4,
      "ranking_seconds": 1.3
    },
    "counts": {
      "queries": 8,
      "sources_found": 15,
      "pages_scraped": 14,
      "documents": 12,
      "spam_filtered": 2,
      "code_snippets": 45,
      "chunks": 128,
      "patterns": 5,
      "stackoverflow": 3
    },
    "quality": {
      "avg_chunk_relevance": 0.782,
      "avg_snippet_relevance": 0.845,
      "content_diversity": 0.733
    },
    "cache": {
      "hits": 3,
      "misses": 12,
      "hit_rate": 0.200
    }
  }
}
```

## ⚙️ Configuration

### Input Schema

```json
{
  "task": "Create a FastAPI endpoint that uploads files to AWS S3",
  "max_sources": 15,
  "allowed_domains": ["fastapi.tiangolo.com", "boto3.amazonaws.com"],
  "include_github": true,
  "include_github_code_search": true,
  "github_token": "ghp_xxx",
  "github_code_languages": ["python", "typescript"],
  "include_stackoverflow": true,
  "max_code_snippets": 20,
  "enable_cache": true,
  "chunk_size": 500,
  "enable_llm_synthesis": true,
  "openrouter_api_key": "sk-or-v1-...",
  "openrouter_model": "arcee-ai/trinity-large-preview:free"
}
```

### Input Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | string | *(required)* | Coding task description |
| `max_sources` | integer | 10 | Maximum sources to scrape (3-50) |
| `allowed_domains` | array | [] | Domain whitelist (empty = all) |
| `include_github` | boolean | true | Enable GitHub repository mining |
| `include_github_code_search` | boolean | true | Enable authenticated GitHub code search |
| `github_token` | string | null | GitHub token (or use `GITHUB_TOKEN` env var) |
| `github_code_languages` | array | [] | Target languages for code search |
| `include_stackoverflow` | boolean | true | Enable StackOverflow Q&A mining |
| `max_code_snippets` | integer | 20 | Maximum code snippets to return (1-100) |
| `enable_cache` | boolean | true | Enable caching for faster repeated runs |
| `chunk_size` | integer | 500 | Token limit per LLM chunk (100-2000) |
| `enable_llm_synthesis` | boolean | true | Enable LLM-powered context synthesis |
| `openrouter_api_key` | string | null | OpenRouter API key (or `OPENROUTER_API_KEY` env var) |
| `openrouter_model` | string | "arcee..." | Model ID to use for LLM synthesis |

## 🏗️ Architecture

### Module Structure

```
src/
├── __main__.py                 # Entry point with input validation
├── orchestrator.py             # Pipeline coordinator with metrics
├── search.py                   # Web search with query expansion
├── github_miner.py             # GitHub repo + code search
├── stackoverflow_miner.py      # StackOverflow Q&A mining
├── crawler.py                  # Async HTTP crawler with retry
├── extractor.py                # Content + code extraction
├── pattern_detector.py         # Implementation pattern detection
├── relevance.py                # Semantic ranking with embeddings
├── chunker.py                  # LLM-optimized text chunking
├── deduplicator.py             # Near-duplicate content removal
├── cache_manager.py            # Apify KV store caching
├── metrics.py                  # Observability and telemetry
└── formatter.py                # Final output formatting
```

### Pipeline Flow

```
Task Input
   ↓
Task Understanding & Query Expansion
   ↓
Multi-Source Discovery (Web + GitHub + StackOverflow)
   ↓
Async Crawling (with retries, timeouts, rate limiting)
   ↓
Content Extraction (readability + BeautifulSoup)
   ↓
Code & Pattern Extraction
   ↓
Content Deduplication (MinHash)
   ↓
Semantic Relevance Ranking (sentence-transformers)
   ↓
LLM-Optimized Chunking (tiktoken)
   ↓
LLM Context Synthesis (OpenRouter API)
   ↓
Structured Context Output + LLM Guidance + Metrics
   ↓
Caching for Future Runs
```

## 📈 Performance

- **Async Architecture**: Concurrent crawling with semaphore limits
- **Smart Caching**: Task-level caching with configurable TTL
- **Batch Processing**: Embeddings computed in batches for efficiency
- **Rate Limiting**: Configurable requests/second throttling
- **Retry Logic**: Exponential backoff for transient failures

## 🔒 Security

- **Input Validation**: Pydantic models with strict typing
- **Token Handling**: Secure environment variable support
- **Content Sanitization**: Readability-lxml for safe HTML parsing
- **SEO Spam Filtering**: Multi-keyword detection (sponsored, affiliate, promo, etc.)
- **Domain Whitelisting**: Optional domain restrictions

## 🛠️ Deployment

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally with test input
python -m src
```

### Apify Deployment

1. Push to Apify:
```bash
apify push
```

2. Configure input in Apify Console or via API:
```bash
apify call <actor-id> --input '{"task": "Build a REST API with FastAPI"}'
```

3. Access results from dataset

### Environment Variables

- `GITHUB_TOKEN`: GitHub personal access token (optional, for code search)
- `OPENROUTER_API_KEY`: API key for OpenRouter LLM synthesis (optional)

## 📦 Dependencies

- `apify` - Actor runtime
- `httpx` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- `readability-lxml` - Content extraction
- `duckduckgo-search` - Web search
- `markdownify` - HTML to Markdown
- `sentence-transformers` - Semantic embeddings
- `tiktoken` - Token counting
- `pydantic` - Input validation
- `rapidfuzz` - Lexical similarity fallback

## 🎯 Use Cases

### AI Coding Assistants
Power your AI coding assistant with real-time context about libraries, patterns, and best practices.

### Developer Copilots
Provide your IDE extension with rich, structured coding context for suggestions.

### Internal Documentation Intelligence
Build RAG systems that combine your internal docs with public knowledge.

### Engineering Onboarding
Generate comprehensive learning materials for new team members on specific technologies.

### Code Review Assistance
Fetch implementation patterns and best practices to guide code reviews.

## 📊 Quality Metrics

The actor provides detailed quality metrics:
- **Relevance Scores**: Average semantic similarity for chunks and snippets
- **Content Diversity**: Unique domain ratio to avoid source bias
- **Cache Efficiency**: Hit rate for performance optimization
- **Timing Breakdown**: Per-phase duration for bottleneck identification

## 🔄 Upgrades from Base Version

### New Features
✅ StackOverflow Q&A Integration
✅ Implementation Pattern Detection
✅ Content Deduplication (MinHash)
✅ Caching Layer (Apify KV Store)
✅ Comprehensive Metrics & Observability
✅ Configurable Pipeline Parameters

### Improvements
✅ Enhanced SEO Spam Filtering
✅ Pattern-Based Code Analysis
✅ Batch Embedding Processing
✅ Content Diversity Scoring
✅ Graceful Error Handling with Metrics

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please submit pull requests or open issues for bugs/features.

---

**Built for production use by AI infrastructure teams.**
