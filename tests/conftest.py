"""Pytest configuration and shared fixtures."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_actor():
    """Mock Apify Actor for testing."""
    actor = MagicMock()
    actor.log = MagicMock()
    actor.log.info = MagicMock()
    actor.log.warning = MagicMock()
    actor.log.error = MagicMock()
    return actor


@pytest.fixture
def sample_task():
    """Sample coding task for testing."""
    return "Build a FastAPI endpoint for uploading files to AWS S3"


@pytest.fixture
def sample_search_results():
    """Sample search results for testing."""
    return [
        {
            "title": "FastAPI File Upload Tutorial",
            "href": "https://fastapi.tiangolo.com/tutorial/request-files/",
            "body": "Learn how to handle file uploads in FastAPI using UploadFile"
        },
        {
            "title": "AWS S3 Python SDK - Boto3",
            "href": "https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html",
            "body": "Upload files to Amazon S3 using the AWS SDK for Python"
        }
    ]


@pytest.fixture
def sample_html_content():
    """Sample HTML content for testing extraction."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>FastAPI File Upload</title></head>
    <body>
        <article>
            <h1>FastAPI File Upload Guide</h1>
            <p>FastAPI provides the UploadFile class for handling file uploads.</p>
            <pre><code class="language-python">
from fastapi import FastAPI, UploadFile

app = FastAPI()

@app.post("/upload/")
async def upload_file(file: UploadFile):
    return {"filename": file.filename}
            </code></pre>
            <p>This is a best practice for handling files asynchronously.</p>
        </article>
    </body>
    </html>
    """


@pytest.fixture
def sample_code_snippets():
    """Sample code snippets for testing."""
    return [
        {
            "language": "python",
            "code": "from fastapi import FastAPI\napp = FastAPI()",
            "description": "FastAPI initialization",
            "source": "https://example.com/1"
        },
        {
            "language": "python",
            "code": "import boto3\ns3 = boto3.client('s3')",
            "description": "S3 client initialization",
            "source": "https://example.com/2"
        }
    ]


@pytest.fixture
def mock_httpx_response():
    """Mock httpx response."""
    response = MagicMock()
    response.status_code = 200
    response.text = "<html><body>Test content</body></html>"
    response.raise_for_status = MagicMock()
    return response


@pytest.fixture
def mock_async_client():
    """Mock async httpx client."""
    client = AsyncMock()
    client.get = AsyncMock()
    return client
