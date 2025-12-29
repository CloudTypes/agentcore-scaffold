# Testing Guide

This directory contains unit tests and integration tests for the AgentCore Voice Agent project.

## Test Structure

```
tests/
├── conftest.py              # Shared pytest fixtures for unit tests
├── unit/                    # Unit tests
│   ├── test_tools/         # Tool tests
│   │   ├── test_calculator.py
│   │   ├── test_database.py
│   │   └── test_weather.py
│   └── test_agent/          # Agent component tests
│       ├── test_websocket_output.py
│       ├── test_websocket_input.py
│       ├── test_agent_factory.py
│       ├── test_endpoints.py
│       └── test_websocket_endpoint.py
├── integration/              # Integration tests
│   ├── conftest.py         # Integration test fixtures
│   ├── test_websocket_flows.py
│   └── README.md           # Integration test documentation
└── README.md                # This file
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run with Coverage

```bash
pytest --cov=src --cov-report=html --cov-report=term
```

This will:
- Generate a terminal coverage report
- Generate an HTML coverage report in `htmlcov/index.html`
- Generate an XML coverage report for CI/CD tools

### Run Specific Test File

```bash
pytest tests/unit/test_tools/test_calculator.py
```

### Run Specific Test

```bash
pytest tests/unit/test_tools/test_calculator.py::TestCalculator::test_valid_addition
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Extra Verbose Output

```bash
pytest -vv
```

### Run Only Fast Tests (Exclude Integration)

```bash
pytest -m "not integration"
```

### Run Only Integration Tests

```bash
pytest tests/integration/
```

Or:

```bash
pytest -m integration
```

## Test Coverage Goals

- **Tools**: 90%+ coverage (pure functions, easy to test)
- **Agent Components**: 80%+ coverage (more complex, requires mocking)
- **Endpoints**: 90%+ coverage (simple HTTP endpoints)

## Test Categories

Tests are organized by type and component:

### Unit Tests

#### Tools (`tests/unit/test_tools/`)

- **Calculator**: Tests for mathematical expression evaluation
- **Database**: Tests for database query operations
- **Weather**: Tests for weather API integration (with mocked HTTP requests)

#### Agent Components (`tests/unit/test_agent/`)

- **WebSocketOutput**: Tests for output event handling and WebSocket communication
- **WebSocketInput**: Tests for input event handling and WebSocket message parsing
- **Agent Factory**: Tests for model and agent creation functions
- **Endpoints**: Tests for HTTP endpoints (health check, root)
- **WebSocket Endpoint**: Tests for WebSocket connection handling (with mocked connections)

### Integration Tests (`tests/integration/`)

Integration tests verify end-to-end WebSocket flows using **real WebSocket connections** while mocking AWS services:

- **Connection Flows**: WebSocket connection establishment and teardown
- **Text Message Flows**: Complete text message exchange cycles
- **Audio Message Flows**: Audio streaming and processing
- **Error Handling**: Error propagation and graceful failure handling
- **Tool Usage Flows**: End-to-end tool usage scenarios

For detailed information about integration tests, see [`tests/integration/README.md`](integration/README.md).

## Mocking Strategy

### Unit Tests

All unit tests use mocks to avoid external dependencies:

- **AWS Services**: `BidiNovaSonicModel` and `BidiAgent` are mocked - no real AWS calls
- **WebSocket**: FastAPI `WebSocket` objects are mocked using `unittest.mock`
- **HTTP Requests**: `requests.get()` is mocked for weather API tests
- **Environment Variables**: Uses `pytest` fixtures with `monkeypatch` or `unittest.mock.patch`

### Integration Tests

Integration tests use a hybrid approach:

- **Real WebSocket Connections**: Use `httpx.AsyncClient` with `ASGITransport` for actual WebSocket protocol testing
- **Mocked AWS Services**: `BidiNovaSonicModel` and `BidiAgent` are mocked to avoid external dependencies
- **Mocked Agent Behavior**: `agent.run()` is mocked to simulate agent responses while testing real WebSocket communication

This approach allows testing:
- Real message serialization/deserialization
- Actual WebSocket protocol behavior
- Integration between WebSocketInput, WebSocketOutput, and the agent
- Connection lifecycle management

Without requiring:
- External AWS services
- Network connectivity
- API keys or credentials

## Writing New Tests

### Unit Tests

When adding new unit tests:

1. Place them in the appropriate directory under `tests/unit/`
2. Use descriptive test class and method names
3. Follow the existing patterns for mocking
4. Ensure tests are isolated and don't require external services
5. Add fixtures to `tests/conftest.py` if they're shared across multiple test files

### Integration Tests

When adding new integration tests:

1. Place them in `tests/integration/`
2. Mark tests with `@pytest.mark.integration`
3. Use real WebSocket connections via `async_client` fixture
4. Mock AWS services but use real WebSocket protocol
5. Add fixtures to `tests/integration/conftest.py` if integration-specific
6. See [`tests/integration/README.md`](integration/README.md) for detailed guidelines

### Example Test Structure

```python
"""
Unit tests for MyComponent.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from my_module import my_function


class TestMyComponent:
    """Test cases for MyComponent."""
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        result = my_function("input")
        assert result == "expected_output"
    
    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Test async functionality."""
        result = await my_async_function("input")
        assert result == "expected_output"
```

## CI/CD Integration

Tests are configured to run in CI/CD pipelines:

- Coverage reports are generated in XML format (`coverage.xml`)
- Unit tests should complete in < 5 seconds total
- Integration tests may take longer (< 30 seconds total)
- All tests must pass before merging
- To run only fast tests in CI: `pytest -m "not integration"`

## Known Warnings

### PytestUnraisableExceptionWarning from AWS CRT

When running integration tests, you may see `PytestUnraisableExceptionWarning` warnings related to AWS CRT (Common Runtime). These warnings are **expected and harmless**. They occur when:

1. AWS services are mocked in tests
2. AWS CRT tries to complete futures that have been cancelled by the mocks
3. pytest's unraisable exception handler detects these cancelled futures

**These warnings do not indicate test failures** and can be safely ignored. They are cosmetic and do not affect test results. Suppression attempts via `filterwarnings` or pytest hooks are not fully effective because these warnings are generated by pytest's unraisable exception handler, not standard Python warnings.

Example warning:
```
PytestUnraisableExceptionWarning: Exception ignored in: <class 'concurrent.futures._base.InvalidStateError'>
  ...
  concurrent.futures._base.InvalidStateError: CANCELLED: <Future at ... state=cancelled>
```

## Troubleshooting

### Import Errors

If you see import errors, ensure you're running tests from the project root:

```bash
cd /path/to/agentcore-voice-agent
pytest
```

### Async Test Issues

If async tests fail, ensure `pytest-asyncio` is installed and `asyncio_mode = auto` is set in `pytest.ini`.

### Coverage Not Showing

If coverage isn't showing correctly:

1. Ensure `pytest-cov` is installed: `pip install pytest-cov`
2. Check that `--cov=src` is in `pytest.ini` or passed as argument
3. Verify source files are in the `src/` directory

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)

