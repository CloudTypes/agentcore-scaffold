# Integration Tests

This directory contains integration tests for end-to-end WebSocket flows in the AgentCore Voice Agent.

## Overview

Integration tests verify the complete flow of data through the WebSocket connection, from client to server and back. Unlike unit tests that mock WebSocket connections, these tests use **real WebSocket connections** via `httpx.AsyncClient` while still mocking AWS services (`BidiNovaSonicModel` and `BidiAgent`) to avoid external dependencies.

## Prerequisites

- Python 3.13+
- All dependencies from `requirements.txt` installed
- No external services required (AWS services are mocked)

## Test Structure

```
tests/integration/
├── __init__.py              # Package initialization
├── conftest.py              # Shared fixtures for integration tests
├── test_websocket_flows.py # Main integration test file
└── README.md                # This file
```

## Running Integration Tests

### Run All Integration Tests

```bash
pytest tests/integration/
```

### Run Specific Test Class

```bash
pytest tests/integration/test_websocket_flows.py::TestTextMessageFlows
```

### Run Specific Test

```bash
pytest tests/integration/test_websocket_flows.py::TestTextMessageFlows::test_text_message_roundtrip
```

### Run with Coverage

```bash
pytest tests/integration/ --cov=src --cov-report=html
```

### Run with Verbose Output

```bash
pytest tests/integration/ -v
```

### Exclude Integration Tests

To run only unit tests (excluding integration tests):

```bash
pytest -m "not integration"
```

## Test Categories

### TestWebSocketConnection

Tests for WebSocket connection establishment:
- `test_websocket_connection_established`: Verifies that WebSocket connections are successfully established and accepted

### TestTextMessageFlows

Tests for text message exchange:
- `test_text_message_roundtrip`: Sends a text message and verifies the complete response cycle
- `test_multiple_text_messages_sequence`: Sends multiple text messages in sequence and verifies each is processed

### TestAudioMessageFlows

Tests for audio message exchange:
- `test_audio_message_roundtrip`: Sends an audio message and verifies audio response
- `test_audio_streaming_multiple_chunks`: Sends multiple audio chunks and verifies they are processed correctly

### TestErrorHandling

Tests for error handling and edge cases:
- `test_invalid_message_format`: Verifies graceful handling of invalid message formats
- `test_agent_error_propagation`: Verifies that agent errors are properly propagated to the client
- `test_websocket_disconnect_graceful`: Tests graceful handling of WebSocket disconnections

### TestToolUsageFlows

Tests for tool usage flows:
- `test_calculator_tool_flow`: Verifies calculator tool usage end-to-end

## Mocking Strategy

### AWS Services

All AWS services are mocked to avoid external dependencies:

- **BidiNovaSonicModel**: Mocked using `unittest.mock.patch` on `agent.create_nova_sonic_model()`
- **BidiAgent**: Mocked using `unittest.mock.patch` on `agent.create_agent()`
- **agent.run()**: Mocked to simulate agent behavior by sending events to the output handler

### Real WebSocket Connections

Integration tests use **real WebSocket connections** via `httpx.AsyncClient` with `ASGITransport`:

```python
async with AsyncClient(
    transport=ASGITransport(app=app),
    base_url="http://test"
) as client:
    async with client.websocket_connect("/ws") as websocket:
        # Test WebSocket communication
```

This ensures that:
- Real WebSocket protocol is tested
- Message serialization/deserialization is verified
- Connection lifecycle is properly tested
- Integration between components is validated

### Mock Agent Behavior

The mock `agent.run()` function simulates agent behavior by:
1. Accepting `inputs` and `outputs` parameters (matching real agent interface)
2. Sending events to the output handler in a configurable sequence
3. Supporting async iteration patterns
4. Handling connection lifecycle events

Example mock agent run:

```python
async def _mock_run(inputs=None, outputs=None):
    if outputs:
        output = outputs[0]
        await output(BidiConnectionStartEvent(...))
        await output(BidiResponseStartEvent(...))
        await output(BidiTranscriptStreamEvent(...))
        await output(BidiResponseCompleteEvent(...))
```

## Test Environment Setup

### Environment Variables

Integration tests use the `mock_env_vars` fixture which sets up required environment variables:

- `AWS_REGION`: "us-east-1"
- `MODEL_ID`: "amazon.nova-sonic-v1:0"
- `VOICE`: "matthew"
- `INPUT_SAMPLE_RATE`: "16000"
- `OUTPUT_SAMPLE_RATE`: "24000"
- `WEATHER_API_KEY`: "test_api_key_12345"
- `SYSTEM_PROMPT`: "You are a helpful voice assistant."

No special environment setup is required - all variables are set by the fixture.

### Module Reloading

Integration tests reload the `agent` module to ensure mocked functions are used:

```python
import agent
importlib.reload(agent)
```

This is necessary because `agent.create_nova_sonic_model()` and `agent.create_agent()` are called at module level in some cases.

## Understanding Test Output

### Successful Test

```
tests/integration/test_websocket_flows.py::TestTextMessageFlows::test_text_message_roundtrip PASSED
```

### Failed Test

If a test fails, the output will show:
- The assertion that failed
- The actual vs expected values
- A traceback showing where the failure occurred

### Timeout Errors

If you see `asyncio.TimeoutError`, it usually means:
- The mock agent didn't send expected events
- The WebSocket connection wasn't established properly
- There's a deadlock in the async code

## Troubleshooting

### Import Errors

If you see import errors, ensure you're running tests from the project root:

```bash
cd /path/to/agentcore-scaffold
pytest tests/integration/
```

### Module Not Reloaded

If tests fail because mocks aren't being used, ensure `importlib.reload(agent)` is called in the test's `finally` block.

### WebSocket Connection Errors

If WebSocket connections fail:
- Ensure `httpx` is installed: `pip install httpx`
- Check that `ASGITransport` is available (part of httpx)
- Verify the FastAPI app is properly imported

### Async Test Issues

If async tests fail:
- Ensure `pytest-asyncio` is installed
- Verify `asyncio_mode = auto` is set in `pytest.ini`
- Check that test functions are marked with `@pytest.mark.asyncio`

## Adding New Integration Tests

### Template

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_my_new_scenario(async_client, mock_env_vars):
    """Test description."""
    async def _mock_run(inputs=None, outputs=None):
        if outputs:
            output = outputs[0]
            # Configure mock behavior
            await output(BidiConnectionStartEvent(...))
            # ... more events
    
    with patch('agent.create_nova_sonic_model') as mock_create_model, \
         patch('agent.create_agent') as mock_create_agent:
        
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model
        
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=_mock_run)
        mock_create_agent.return_value = mock_agent
        
        import agent
        importlib.reload(agent)
        
        try:
            async with async_client.websocket_connect("/ws") as websocket:
                # Test implementation
                await websocket.send_json({"text": "test"})
                message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
                assert message["type"] == "expected_type"
        finally:
            importlib.reload(agent)
```

### Best Practices

1. **Always reload the agent module** in a `try/finally` block to ensure clean state
2. **Use timeouts** when waiting for messages: `asyncio.wait_for(websocket.receive_json(), timeout=2.0)`
3. **Mock agent behavior** to send realistic event sequences
4. **Test both success and error paths**
5. **Use descriptive test names** that explain what is being tested
6. **Group related tests** into test classes

## When to Use Integration vs Unit Tests

### Use Integration Tests For:
- End-to-end WebSocket flows
- Message serialization/deserialization
- Connection lifecycle
- Integration between WebSocketInput, WebSocketOutput, and agent
- Real protocol behavior

### Use Unit Tests For:
- Individual component behavior
- Error handling in isolated components
- Fast feedback during development
- Testing edge cases in specific functions

## CI/CD Integration

Integration tests are designed to:
- Run in CI/CD pipelines without external dependencies
- Complete in reasonable time (< 30 seconds total)
- Provide clear failure messages
- Generate coverage reports

To exclude integration tests from fast CI runs:

```bash
pytest -m "not integration"
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [httpx Documentation](https://www.python-httpx.org/)
- [FastAPI Testing Documentation](https://fastapi.tiangolo.com/advanced/testing-websockets/)

