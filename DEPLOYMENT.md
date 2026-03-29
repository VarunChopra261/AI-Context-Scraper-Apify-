# Deployment Guide - AI Context Scraper Actor

## Prerequisites

- Python 3.10 or higher
- Docker (for containerized deployment)
- Apify account (for Apify platform deployment)
- GitHub personal access token (optional, for code search)

## Local Development

### 1. Setup Environment

```bash
# Clone repository
git clone <repository-url>
cd ai-context-scraper-actor

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows
.venv\Scripts\activate
# On Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your tokens
# Required: APIFY_TOKEN
# Optional: GITHUB_TOKEN
```

### 3. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov --cov-report=html

# Run specific test file
pytest tests/test_chunker.py
```

### 4. Run Locally

```bash
# Run the actor
python -m src

# Or use Make
make run
```

## Docker Deployment

### Build Docker Image

```bash
# Build image
docker build -t ai-context-scraper:latest .

# Test image
docker run --rm -e APIFY_TOKEN=$APIFY_TOKEN ai-context-scraper:latest
```

### Run with Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'
services:
  ai-context-scraper:
    build: .
    environment:
      - APIFY_TOKEN=${APIFY_TOKEN}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
    volumes:
      - ./storage:/app/storage
```

Run:
```bash
docker-compose up
```

## Apify Platform Deployment

### 1. Install Apify CLI

```bash
npm install -g apify-cli
```

### 2. Login to Apify

```bash
apify login
```

### 3. Initialize Actor (if not already done)

```bash
apify init
```

### 4. Deploy to Apify

```bash
# Deploy to production
apify push

# Deploy as beta version
apify push --build-tag beta

# Deploy with version tag
apify push --version-number 1.0.0
```

### 5. Configure Actor in Apify Console

1. Go to https://console.apify.com/actors
2. Find your actor
3. Configure environment variables:
   - `GITHUB_TOKEN` (if using GitHub code search)
4. Set resource limits:
   - Memory: 2048 MB (recommended)
   - Timeout: 300 seconds

### 6. Test Actor

```bash
# Run actor via CLI
apify call <actor-id> --input '{
  "task": "Build a FastAPI endpoint",
  "max_sources": 15,
  "include_github": true,
  "enable_cache": true
}'

# Or use Apify API
curl -X POST https://api.apify.com/v2/acts/<actor-id>/runs \
  -H "Authorization: Bearer $APIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Build a FastAPI endpoint",
    "max_sources": 15
  }'
```

## Production Checklist

### Before Deployment

- [ ] All tests passing (`pytest`)
- [ ] Code formatted (`black src tests`)
- [ ] Linting clean (`ruff check src tests`)
- [ ] Type checking passes (`mypy src`)
- [ ] Security scan clean (`bandit -r src`)
- [ ] Dependencies up to date (`pip list --outdated`)
- [ ] Environment variables configured
- [ ] Docker image builds successfully
- [ ] Documentation updated

### After Deployment

- [ ] Test with sample inputs
- [ ] Monitor initial runs for errors
- [ ] Check Actor logs in Apify Console
- [ ] Verify metrics collection
- [ ] Test error handling with invalid inputs
- [ ] Validate output format
- [ ] Check resource usage (memory, CPU)
- [ ] Set up monitoring/alerts

## Environment Variables Reference

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `APIFY_TOKEN` | Apify API token | `apify_api_xxx` |

### Optional

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `GITHUB_TOKEN` | GitHub PAT for code search | None | `ghp_xxx` |
| `MAX_SOURCES` | Max sources to scrape | 10 | `15` |
| `CHUNK_SIZE` | Token limit per chunk | 500 | `500` |
| `ENABLE_CACHE` | Enable caching | true | `true` |
| `LOG_LEVEL` | Logging level | INFO | `DEBUG` |
| `RATE_LIMIT_RPS` | Requests per second | 10 | `10` |

## Monitoring and Debugging

### View Logs

```bash
# Local
tail -f actor.log

# Apify CLI
apify runs <run-id>

# Apify API
curl "https://api.apify.com/v2/actor-runs/<run-id>/log" \
  -H "Authorization: Bearer $APIFY_TOKEN"
```

### Common Issues

**Issue**: Actor times out
- **Solution**: Reduce `max_sources` or increase timeout in Apify Console

**Issue**: GitHub rate limit exceeded
- **Solution**: Provide `GITHUB_TOKEN` for higher rate limits

**Issue**: Out of memory
- **Solution**: Increase memory limit in Apify Console to 4096 MB

**Issue**: Cache not working
- **Solution**: Verify `APIFY_TOKEN` is set and has KV store access

## Performance Optimization

### For Faster Runs

1. Enable caching: `"enable_cache": true`
2. Reduce sources: `"max_sources": 10`
3. Use domain whitelist: `"allowed_domains": ["python.org"]`
4. Disable optional features if not needed

### For Better Quality

1. Increase sources: `"max_sources": 20`
2. Enable all features: GitHub + StackOverflow
3. Use language targeting for code search
4. Increase chunk size for more context

## Scaling Considerations

### Horizontal Scaling

- Apify platform handles scaling automatically
- Configure max concurrent runs in Apify Console
- Use Apify dataset for result aggregation

### Cost Optimization

- Enable caching to reduce redundant API calls
- Use domain whitelisting to focus crawling
- Set conservative timeouts
- Monitor compute units usage in Apify Console

## Security Best Practices

1. **Never commit tokens** - Use environment variables
2. **Rotate tokens regularly** - Update GITHUB_TOKEN every 90 days
3. **Use read-only tokens** - GitHub PAT needs only `repo:read` scope
4. **Enable HTTPS enforcement** - Set `ENFORCE_HTTPS=true` in production
5. **Review dependencies** - Run `safety check` before deployment
6. **Monitor for vulnerabilities** - Enable GitHub Dependabot alerts

## Backup and Recovery

### Backup Data

```bash
# Export Apify dataset
apify dataset export <dataset-id> --format json > backup.json

# Backup KV store
apify kvs get <key> > backup-cache.json
```

### Restore Data

```bash
# Import to dataset
apify dataset push-items backup.json
```

## Support

- **Issues**: GitHub Issues
- **Email**: support@example.com
- **Documentation**: README.md
- **Apify Support**: https://docs.apify.com

## Version History

- **v2.0.0** - Production-grade upgrade with tests, caching, patterns
- **v1.1.0** - Added GitHub code search and language targeting
- **v1.0.0** - Initial release with basic scraping
