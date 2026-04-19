# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| 1.1.x   | :white_check_mark: |
| < 1.1   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in AI Context Scraper, please report it by emailing **late120872@gmail.com**.

Please **DO NOT** open a public issue for security vulnerabilities.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Critical issues within 14 days, others within 30 days

## Security Measures

### Input Validation

- All inputs validated with Pydantic models
- URL validation and sanitization
- Domain whitelisting support
- Maximum limits on all parameters

### Output Sanitization

- HTML content cleaned with readability-lxml
- Script tags removed
- XSS prevention in markdown conversion
- SEO spam filtering

### Dependency Security

- Regular dependency updates
- Safety checks in CI/CD pipeline
- Bandit security scanning
- No known vulnerabilities in dependencies

### Authentication

- Secure token handling via environment variables
- No tokens in logs or error messages
- Read-only GitHub token scope recommended
- Token rotation supported

### Network Security

- HTTPS enforcement option
- Rate limiting to prevent abuse
- Timeout controls
- User agent identification

### Data Privacy

- No PII collection
- Source URLs logged for attribution only
- Optional caching (can be disabled)
- Data retention controlled by Apify platform

## Best Practices for Users

1. **Token Management**
   - Never commit tokens to version control
   - Use environment variables or secret managers
   - Rotate tokens every 90 days
   - Use minimum required scopes

2. **Access Control**
   - Restrict Apify Actor access to authorized users
   - Use read-only tokens when possible
   - Monitor actor usage logs

3. **Input Validation**
   - Validate task descriptions before submission
   - Use domain whitelisting in production
   - Set conservative resource limits

4. **Monitoring**
   - Enable logging and monitoring
   - Review security audit reports
   - Check for dependency updates weekly

## Known Limitations

1. **External Dependencies**
   - Relies on third-party APIs (GitHub, StackOverflow, DuckDuckGo)
   - Subject to rate limits and availability
   - Cannot control third-party data quality

2. **Content Risks**
   - Scraped content may contain malicious links
   - SEO spam filter may not catch all spam
   - Users responsible for validating scraped content

3. **Resource Consumption**
   - Large tasks may consume significant memory
   - No hard limit on embedding computation
   - Caching may accumulate large datasets

## Security Audit History

| Date | Type | Findings | Status |
|------|------|----------|--------|
| 2024-12 | Code Scan | None | ✅ Clean |
| 2024-12 | Dependency | None | ✅ Clean |
| 2024-12 | Penetration Test | Pending | 🟡 Scheduled |

## Compliance

- **GDPR**: No personal data collected
- **CCPA**: Not applicable (no consumer data)
- **Terms of Service**: Users must comply with scraped site terms

## Security Contacts

- **Maintainer**: late120872@gmail.com

## Acknowledgments

We thank the security research community for responsible disclosure.

### Hall of Fame

- (No vulnerabilities reported yet)

---

**Last Updated**: December 2024
