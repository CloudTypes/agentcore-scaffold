# AgentCore Bi-Directional Streaming Voice Agent

A production-ready voice agent with bi-directional streaming using Amazon Bedrock AgentCore Runtime and Strands framework.

## 🚀 Quick Start

### Prerequisites
- AWS Account with credentials configured
- Python 3.10+
- Docker (optional)
- Amazon Nova Sonic model access enabled
- **macOS users**: Install PortAudio via Homebrew: `brew install portaudio`

### Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your AWS credentials
```

### Run Locally

```bash
# Start the agent
python src/agent.py

# In another terminal, open the web client
open client/web/index.html
```

### Deploy to AgentCore Runtime

#### Using AgentCore CLI

```bash
# Install CLI
pip install bedrock-agentcore-starter-toolkit

# Configure and deploy
agentcore configure -e src/agent.py
agentcore launch

# Test deployed agent
agentcore invoke '{"prompt": "Hello!"}'
```

#### Building Docker Image

The Dockerfile includes PortAudio (`portaudio19-dev`) as a system dependency, which is required for the `pyaudio` Python package used by the Strands library.

**Note:** AgentCore Runtime requires ARM64 architecture. Build your Docker image accordingly:

```bash
# Build for ARM64 (required for AgentCore Runtime)
docker buildx build --platform linux/arm64 -t agentcore-voice-agent:latest .

# Or if using Docker Desktop with buildx
docker build --platform linux/arm64 -t agentcore-voice-agent:latest .
```

The Dockerfile automatically installs:
- PortAudio development libraries (`portaudio19-dev`)
- Audio processing libraries (`libsndfile1`)
- Compiler tools needed for building Python packages

## 📚 Documentation

- See `docs/` folder for detailed documentation
- [AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
- [AWS Blog Post](https://aws.amazon.com/blogs/machine-learning/bi-directional-streaming-for-real-time-agent-interactions-now-available-in-amazon-bedrock-agentcore-runtime/)

## 🔧 Features

- ✅ Bi-directional streaming with WebSocket
- ✅ Real-time voice conversations
- ✅ Tool integration (calculator, weather, database)
- ✅ Production-ready with health checks
- ✅ Docker containerization
- ✅ Web test client included
- ✅ Comprehensive unit test suite

## 🧪 Testing

The project includes a comprehensive unit test suite. See [tests/README.md](tests/README.md) for detailed testing documentation.

### Quick Start

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=html --cov-report=term

# Run specific test file
pytest tests/unit/test_tools/test_calculator.py
```

### Test Coverage

- Tools: 90%+ coverage
- Agent Components: 80%+ coverage
- Endpoints: 90%+ coverage

## 📄 License

Apache 2.0
