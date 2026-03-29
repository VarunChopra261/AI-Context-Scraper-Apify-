# Contributing to AI Context Scraper

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

## How to Contribute

### Reporting Bugs

1. **Check existing issues** to avoid duplicates
2. **Use the issue template** when creating new issues
3. **Provide detailed information**:
   - Python version
   - Operating system
   - Steps to reproduce
   - Expected vs actual behavior
   - Error messages and stack traces

### Suggesting Enhancements

1. **Check the roadmap** to see if it's already planned
2. **Describe the use case** clearly
3. **Explain why this enhancement would be useful**
4. **Provide examples** if applicable

### Pull Requests

#### Before You Start

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Check existing PRs** to avoid duplicates

#### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/ai-context-scraper-actor.git
cd ai-context-scraper-actor

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development tools
pip install black ruff pylint mypy pytest pytest-cov
```

#### Development Workflow

1. **Make your changes**
2. **Write/update tests**
3. **Run tests**: `pytest`
4. **Format code**: `black src tests`
5. **Lint code**: `ruff check src tests`
6. **Type check**: `mypy src`
7. **Update documentation** if needed

#### Pull Request Process

1. **Commit your changes** with clear messages
   ```bash
   git commit -m "feat: add new pattern detection for X"
   ```

2. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

3. **Create Pull Request** with:
   - Clear title and description
   - Link to related issues
   - Screenshots/examples if applicable
   - Checklist from template

4. **Respond to review feedback**
5. **Wait for approval** from maintainers

#### Commit Message Format

Follow conventional commits:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting)
- `refactor:` - Code refactoring
- `test:` - Adding/updating tests
- `chore:` - Maintenance tasks

Examples:
```
feat: add support for TypeScript pattern detection
fix: resolve memory leak in chunker module
docs: update deployment guide with Docker instructions
test: add edge case tests for deduplicator
```

## Development Guidelines

### Code Style

- Follow [PEP 8](https://pep8.org/)
- Use Black for formatting (line length: 100)
- Use type hints
- Write docstrings for public functions

### Testing

- Write tests for new features
- Maintain >80% code coverage
- Include edge cases and error scenarios
- Use meaningful test names

Example:
```python
def test_deduplicate_removes_exact_duplicates():
    """Test that exact duplicates are removed correctly."""
    # Test implementation
```

### Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions/classes
- Update DEPLOYMENT.md for operational changes
- Include examples in docstrings

### Performance

- Avoid unnecessary computations
- Use async/await for I/O operations
- Batch operations when possible
- Profile code for bottlenecks

### Security

- Validate all user inputs
- Sanitize before logging
- Never commit secrets/tokens
- Follow security best practices

## Project Structure

```
ai-context-scraper-actor/
├── .actor/              # Apify actor metadata
├── .github/             # GitHub workflows
├── src/                 # Source code
│   ├── __main__.py     # Entry point
│   ├── orchestrator.py # Main coordinator
│   ├── [modules].py    # Feature modules
│   ├── security.py     # Security utilities
│   └── exceptions.py   # Custom exceptions
├── tests/              # Test suite
├── requirements.txt    # Dependencies
├── pytest.ini         # Pytest configuration
├── pyproject.toml     # Tool configuration
└── README.md          # User documentation
```

## Testing Your Changes

### Unit Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_chunker.py

# Run with coverage
pytest --cov=src --cov-report=html
```

### Integration Testing

```bash
# Test with sample input
python -m src <<< '{"task": "Build a REST API"}'

# Test Docker build
docker build -t test .
docker run --rm -e APIFY_TOKEN test
```

### Manual Testing

1. Test with various inputs
2. Verify output format
3. Check error handling
4. Monitor resource usage

## Release Process

(For maintainers)

1. Update version in `.actor/actor.json`
2. Update CHANGELOG.md
3. Create release branch: `release/vX.Y.Z`
4. Run full test suite
5. Build and test Docker image
6. Merge to main
7. Tag release: `git tag vX.Y.Z`
8. Deploy to Apify
9. Announce release

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Security**: Email security@example.com
- **General**: Contact maintainers

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in documentation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Thank You!

Your contributions make this project better for everyone. We appreciate your time and effort! 🎉
