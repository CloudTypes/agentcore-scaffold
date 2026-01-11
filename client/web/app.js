let websocket = null;
let audioContext = null;
let audioStream = null;
let scriptProcessor = null;
let isMuted = false;
let lastInputWasText = false;  // Track if last input was text

// Audio playback queue
let audioQueue = [];
let isPlayingAudio = false;

// Track last messages to avoid duplicates
let lastUserMessage = null;
let lastAgentMessage = null;

// Authentication state
let authToken = null;
let currentUser = null;

// Session and mode state
let currentSessionId = null;
let currentMode = 'voice'; // 'voice' or 'text'
let orchestratorConnected = false;

/**
 * Get the base URL for the voice agent API.
 * 
 * Supports runtime configuration via window.API_BASE for CloudFront/API Gateway
 * deployments. Falls back to current origin for same-origin requests, or
 * localhost:8080 for local file:// protocol usage.
 * 
 * @returns {string} Base URL for voice agent API (e.g., "https://api.example.com" or "http://localhost:8080")
 */
const getApiBase = () => {
    // Support runtime configuration (for CloudFront/API Gateway)
    if (window.API_BASE) return window.API_BASE;
    if (window.location.protocol === 'file:' || !window.location.origin || window.location.origin === 'null') {
        return 'http://localhost:8080';
    }
    return window.location.origin;
};

/**
 * Get the base URL for the orchestrator agent API.
 * 
 * Supports runtime configuration via window.ORCHESTRATOR_BASE. If not configured,
 * derives from API_BASE by replacing port 8080 with 9000.
 * 
 * @returns {string} Base URL for orchestrator agent API (e.g., "https://api.example.com:9000" or "http://localhost:9000")
 */
const getOrchestratorBase = () => {
    // Support runtime configuration
    if (window.ORCHESTRATOR_BASE) return window.ORCHESTRATOR_BASE;
    // Default: derive from API_BASE (replace port 8080 with 9000)
    const apiBase = getApiBase();
    return apiBase.replace(':8080', ':9000').replace('8080', '9000');
};

/**
 * Get the base URL for WebSocket connections.
 * 
 * Supports runtime configuration via window.WS_BASE. If not configured,
 * converts HTTP/HTTPS protocol to WS/WSS protocol from API_BASE.
 * 
 * @returns {string} WebSocket base URL (e.g., "wss://api.example.com" or "ws://localhost:8080")
 */
const getWsBase = () => {
    // Support runtime configuration
    if (window.WS_BASE) return window.WS_BASE;
    // Convert HTTP/HTTPS to WS/WSS
    const apiBase = getApiBase();
    const wsProtocol = apiBase.startsWith('https') ? 'wss:' : 'ws:';
    const wsHost = apiBase.replace(/^https?:/, '').replace(/^\/\//, '');
    return `${wsProtocol}//${wsHost}`;
};

const API_BASE = getApiBase();
const ORCHESTRATOR_BASE = getOrchestratorBase();
const WS_BASE = getWsBase();

const statusEl = document.getElementById('status');
const messagesEl = document.getElementById('messages');
const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const muteBtn = document.getElementById('muteBtn');
const sendTextBtn = document.getElementById('sendTextBtn');
const textInput = document.getElementById('textInput');

// Authentication functions
async function login() {
    window.location.href = `${API_BASE}/api/auth/login`;
}

async function logout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('authToken');
    updateAuthUI();
    if (websocket) {
        disconnect();
    }
}

async function checkAuth() {
    // Check for token in URL (from OAuth callback)
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    if (token) {
        authToken = token;
        localStorage.setItem('authToken', token);
        // Remove token from URL
        window.history.replaceState({}, document.title, window.location.pathname);
        await loadUserInfo();
    } else {
        // Try to load from localStorage
        authToken = localStorage.getItem('authToken');
        if (authToken) {
            await loadUserInfo();
        }
    }
    updateAuthUI();
}

async function loadUserInfo() {
    if (!authToken) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/auth/me`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            currentUser = await response.json();
        } else {
            // Token invalid, clear it
            authToken = null;
            localStorage.removeItem('authToken');
            currentUser = null;
        }
    } catch (error) {
        console.error('Error loading user info:', error);
        authToken = null;
        localStorage.removeItem('authToken');
        currentUser = null;
    }
}

function updateAuthUI() {
    const loginSection = document.getElementById('loginSection');
    const userSection = document.getElementById('userSection');
    
    if (currentUser && authToken) {
        loginSection.style.display = 'none';
        userSection.style.display = 'block';
        document.getElementById('userName').textContent = currentUser.name || currentUser.email;
        document.getElementById('userEmail').textContent = currentUser.email;
        if (currentUser.picture) {
            document.getElementById('userPicture').src = currentUser.picture;
        }
        connectBtn.disabled = false;
    } else {
        loginSection.style.display = 'block';
        userSection.style.display = 'none';
        connectBtn.disabled = true;
    }
}

// Tab management
function showTab(tab) {
    const chatContent = document.getElementById('chatContent');
    const memoryContent = document.getElementById('memoryContent');
    const chatTab = document.getElementById('chatTab');
    const memoryTab = document.getElementById('memoryTab');
    
    if (tab === 'chat') {
        chatContent.style.display = 'block';
        memoryContent.style.display = 'none';
        chatTab.style.background = '#007bff';
        memoryTab.style.background = '#6c757d';
    } else {
        chatContent.style.display = 'none';
        memoryContent.style.display = 'block';
        chatTab.style.background = '#6c757d';
        memoryTab.style.background = '#007bff';
    }
}

// Accordion management
function toggleAccordion(sectionId) {
    const content = document.getElementById(sectionId);
    const icon = document.getElementById(sectionId + 'Icon');
    
    if (content.style.display === 'none' || !content.style.display) {
        content.style.display = 'block';
        if (icon) icon.textContent = '▼';
    } else {
        content.style.display = 'none';
        if (icon) icon.textContent = '▶';
    }
}

// Memory API functions
async function queryMemories() {
    const query = document.getElementById('memoryQuery').value;
    const memoryTypeSelect = document.getElementById('memoryTypeSelect');
    const memoryType = memoryTypeSelect ? memoryTypeSelect.value : 'all';
    const namespaceInput = document.getElementById('namespaceInput');
    const namespace = namespaceInput && namespaceInput.value.trim() ? namespaceInput.value.trim() : null;
    
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    const resultsDiv = document.getElementById('memoryResults');
    resultsDiv.innerHTML = '<p>Searching...</p>';
    
    try {
        const requestBody = {
            query: query || '',
            top_k: 10
        };
        
        // Add memory_type if not 'all'
        if (memoryType && memoryType !== 'all') {
            requestBody.memory_type = memoryType;
        }
        
        // Add namespace if provided
        if (namespace) {
            requestBody.namespace = namespace;
        }
        
        const response = await fetch(`${API_BASE}/api/memory/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(requestBody)
        });
        
        if (response.ok) {
            const data = await response.json();
            resultsDiv.innerHTML = `<h4>Search Results (${data.memories ? data.memories.length : 0} found):</h4>`;
            if (data.memories && data.memories.length > 0) {
                data.memories.forEach((mem, index) => {
                    const memDiv = document.createElement('div');
                    memDiv.style.padding = '10px';
                    memDiv.style.margin = '5px 0';
                    memDiv.style.background = 'white';
                    memDiv.style.borderRadius = '5px';
                    memDiv.style.border = '1px solid #ddd';
                    
                    const headerDiv = document.createElement('div');
                    headerDiv.style.display = 'flex';
                    headerDiv.style.justifyContent = 'space-between';
                    headerDiv.style.alignItems = 'center';
                    headerDiv.style.marginBottom = '5px';
                    
                    const namespaceDiv = document.createElement('div');
                    namespaceDiv.style.fontSize = '12px';
                    namespaceDiv.style.color = '#666';
                    namespaceDiv.textContent = `Namespace: ${mem.namespace || 'N/A'}`;
                    headerDiv.appendChild(namespaceDiv);
                    
                    const expandBtn = document.createElement('button');
                    expandBtn.textContent = 'View Full';
                    expandBtn.style.background = '#6c757d';
                    expandBtn.style.color = 'white';
                    expandBtn.style.border = 'none';
                    expandBtn.style.padding = '3px 8px';
                    expandBtn.style.borderRadius = '3px';
                    expandBtn.style.cursor = 'pointer';
                    expandBtn.style.fontSize = '11px';
                    expandBtn.onclick = () => {
                        const fullContent = document.getElementById(`fullContent_${index}`);
                        if (fullContent.style.display === 'none') {
                            fullContent.style.display = 'block';
                            expandBtn.textContent = 'Hide Full';
                        } else {
                            fullContent.style.display = 'none';
                            expandBtn.textContent = 'View Full';
                        }
                    };
                    headerDiv.appendChild(expandBtn);
                    
                    memDiv.appendChild(headerDiv);
                    
                    const contentDiv = document.createElement('div');
                    const contentText = mem.content || JSON.stringify(mem);
                    const preview = contentText.length > 200 ? contentText.substring(0, 200) + '...' : contentText;
                    contentDiv.textContent = preview;
                    memDiv.appendChild(contentDiv);
                    
                    const fullContent = document.createElement('div');
                    fullContent.id = `fullContent_${index}`;
                    fullContent.style.display = 'none';
                    fullContent.style.marginTop = '10px';
                    fullContent.style.padding = '10px';
                    fullContent.style.background = '#f8f9fa';
                    fullContent.style.borderRadius = '3px';
                    fullContent.style.whiteSpace = 'pre-wrap';
                    fullContent.style.fontSize = '12px';
                    fullContent.textContent = contentText;
                    memDiv.appendChild(fullContent);
                    
                    resultsDiv.appendChild(memDiv);
                });
            } else {
                resultsDiv.innerHTML += '<p>No memories found.</p>';
            }
        } else {
            const errorText = await response.text();
            resultsDiv.innerHTML = `<p style="color: red;">Error querying memories: ${errorText}</p>`;
        }
    } catch (error) {
        console.error('Error querying memories:', error);
        resultsDiv.innerHTML = `<p style="color: red;">Error querying memories: ${error.message}</p>`;
    }
}

async function loadPreferences() {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/preferences`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            const prefsDiv = document.getElementById('preferences');
            prefsDiv.innerHTML = '<h4>User Preferences:</h4>';
            if (data.preferences && data.preferences.length > 0) {
                data.preferences.forEach(pref => {
                    const prefDiv = document.createElement('div');
                    prefDiv.style.padding = '10px';
                    prefDiv.style.margin = '5px 0';
                    prefDiv.style.background = 'white';
                    prefDiv.style.borderRadius = '5px';
                    prefDiv.style.border = '1px solid #ddd';
                    
                    if (pref.namespace) {
                        const namespaceDiv = document.createElement('div');
                        namespaceDiv.style.fontSize = '12px';
                        namespaceDiv.style.color = '#666';
                        namespaceDiv.style.marginBottom = '5px';
                        namespaceDiv.textContent = `Namespace: ${pref.namespace}`;
                        prefDiv.appendChild(namespaceDiv);
                    }
                    
                    const contentDiv = document.createElement('div');
                    contentDiv.textContent = pref.content || JSON.stringify(pref);
                    prefDiv.appendChild(contentDiv);
                    
                    prefsDiv.appendChild(prefDiv);
                });
            } else {
                prefsDiv.innerHTML += '<p>No preferences found.</p>';
            }
        } else {
            const errorText = await response.text();
            alert(`Error loading preferences: ${errorText}`);
        }
    } catch (error) {
        console.error('Error loading preferences:', error);
        alert('Error loading preferences: ' + error.message);
    }
}

async function loadSessions() {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    const sessionsDiv = document.getElementById('sessions');
    sessionsDiv.innerHTML = '<p>Loading sessions...</p>';
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/sessions`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            sessionsDiv.innerHTML = `<h4>Sessions (${data.sessions ? data.sessions.length : 0} found):</h4>`;
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(session => {
                    const sessionDiv = document.createElement('div');
                    sessionDiv.style.padding = '10px';
                    sessionDiv.style.margin = '5px 0';
                    sessionDiv.style.background = 'white';
                    sessionDiv.style.borderRadius = '5px';
                    sessionDiv.style.border = '1px solid #ddd';
                    
                    // Extract session_id and summary - backend returns these fields
                    const sessionId = session.session_id || session.id || 'Unknown';
                    const summary = session.summary || 'No summary available';
                    
                    const headerDiv = document.createElement('div');
                    headerDiv.style.display = 'flex';
                    headerDiv.style.justifyContent = 'space-between';
                    headerDiv.style.alignItems = 'center';
                    headerDiv.style.marginBottom = '5px';
                    
                    const sessionIdDiv = document.createElement('div');
                    sessionIdDiv.style.fontWeight = 'bold';
                    sessionIdDiv.textContent = `Session: ${sessionId}`;
                    headerDiv.appendChild(sessionIdDiv);
                    
                    const viewBtn = document.createElement('button');
                    viewBtn.textContent = 'View Details';
                    viewBtn.style.background = '#007bff';
                    viewBtn.style.color = 'white';
                    viewBtn.style.border = 'none';
                    viewBtn.style.padding = '5px 10px';
                    viewBtn.style.borderRadius = '3px';
                    viewBtn.style.cursor = 'pointer';
                    viewBtn.onclick = () => viewSessionDetails(sessionId);
                    headerDiv.appendChild(viewBtn);
                    
                    sessionDiv.appendChild(headerDiv);
                    
                    const summaryDiv = document.createElement('div');
                    summaryDiv.style.fontSize = '14px';
                    summaryDiv.style.color = '#666';
                    summaryDiv.textContent = summary.length > 100 ? summary.substring(0, 100) + '...' : summary;
                    sessionDiv.appendChild(summaryDiv);
                    
                    sessionsDiv.appendChild(sessionDiv);
                });
            } else {
                sessionsDiv.innerHTML += '<p>No sessions found.</p>';
            }
        } else {
            const errorText = await response.text();
            sessionsDiv.innerHTML = `<p style="color: red;">Error loading sessions: ${errorText}</p>`;
        }
    } catch (error) {
        console.error('Error loading sessions:', error);
        sessionsDiv.innerHTML = `<p style="color: red;">Error loading sessions: ${error.message}</p>`;
    }
}

async function viewSessionDetails(sessionId) {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/sessions/${sessionId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            const modal = document.getElementById('sessionModal');
            const contentDiv = document.getElementById('sessionDetailContent');
            
            contentDiv.innerHTML = `
                <div style="margin-bottom: 15px;">
                    <strong>Session ID:</strong> ${data.session_id}
                </div>
                ${data.namespace ? `<div style="margin-bottom: 15px;"><strong>Namespace:</strong> ${data.namespace}</div>` : ''}
                <div style="margin-bottom: 15px;">
                    <strong>Summary:</strong>
                    <div style="margin-top: 10px; padding: 10px; background: #f8f9fa; border-radius: 5px; white-space: pre-wrap;">${data.summary || 'No summary available'}</div>
                </div>
            `;
            
            modal.style.display = 'block';
        } else if (response.status === 404) {
            alert('Session not found');
        } else {
            const errorText = await response.text();
            alert(`Error loading session details: ${errorText}`);
        }
    } catch (error) {
        console.error('Error loading session details:', error);
        alert('Error loading session details: ' + error.message);
    }
}

function closeSessionModal() {
    const modal = document.getElementById('sessionModal');
    modal.style.display = 'none';
}

// Close modal when clicking outside of it
window.onclick = function(event) {
    const modal = document.getElementById('sessionModal');
    if (event.target === modal) {
        closeSessionModal();
    }
}

/**
 * Create a new session or return existing session ID.
 * 
 * This function checks if a session already exists. If it does, it returns the
 * existing session_id to maintain conversation continuity. If not, it creates
 * a new session by calling the /api/sessions endpoint.
 * 
 * @async
 * @returns {Promise<string>} The session ID (either existing or newly created)
 * @throws {Error} If session creation fails or authentication is invalid
 */
async function createSession() {
    if (currentSessionId) {
        return currentSessionId; // Reuse existing session
    }
    
    if (!authToken) {
        throw new Error('Please login first');
    }
    
    const response = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${authToken}` // Use header, not query param
        }
    });
    
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to create session: ${errorText}`);
    }
    
    const data = await response.json();
    currentSessionId = data.session_id;
    return currentSessionId;
}

/**
 * Connect to voice agent via WebSocket.
 * 
 * Creates a session if needed, then establishes a WebSocket connection to the
 * voice agent for bi-directional audio streaming. The session_id is passed
 * as a query parameter to maintain conversation context.
 * 
 * @async
 * @returns {Promise<void>}
 * @throws {Error} If session creation fails or WebSocket connection fails
 */
async function connectVoiceMode() {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    await createSession(); // Creates only if needed
    
    // WebSocket connection - use configurable WS_BASE
    // Note: WebSocket may still use query params for token (API Gateway WebSocket API supports this)
    const wsUrl = `${WS_BASE}/ws?token=${encodeURIComponent(authToken)}&session_id=${currentSessionId}`;
    websocket = new WebSocket(wsUrl);
    
    websocket.onopen = async () => {
        updateStatus('connected');
        // Don't add connection message - status indicator is sufficient
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
        muteBtn.disabled = false;
        sendTextBtn.disabled = false;
        
        // Initialize mode indicator
        updateInputModeIndicator('voice');
        
        // Auto-start recording for bi-directional streaming
        await startRecording();
    };
    
    websocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleAgentResponse(data);
        } catch (error) {
            console.error('Error parsing message from server:', error);
        }
    };
    
    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        addMessage('Error', 'Connection error occurred', 'error');
    };
    
    websocket.onclose = () => {
        updateStatus('disconnected');
        addMessage('System', 'Disconnected from voice agent', 'agent');
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
        muteBtn.disabled = true;
        sendTextBtn.disabled = true;
        stopRecording();
    };
}

/**
 * Connect to orchestrator agent in text mode.
 * 
 * Creates a session if needed, then enables text input UI. No WebSocket
 * connection is established for text mode - communication happens via
 * HTTP POST requests to the orchestrator agent.
 * 
 * @async
 * @returns {Promise<void>}
 * @throws {Error} If session creation fails
 */
async function connectTextMode() {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    await createSession(); // Creates only if needed
    
    // No WebSocket needed, just enable UI
    updateStatus('connected');
    orchestratorConnected = true;
    connectBtn.disabled = true;
    disconnectBtn.disabled = false;
    muteBtn.disabled = true; // Mute button not applicable in text mode
    sendTextBtn.disabled = false;
    updateInputModeIndicator('text');
}

/**
 * Switch between voice and text modes while maintaining session continuity.
 * 
 * This function handles mode switching by disconnecting the current connection
 * (if active), updating the mode, and reconnecting in the new mode using the
 * existing session_id. This preserves conversation history and context across
 * mode switches.
 * 
 * @async
 * @param {string} newMode - The mode to switch to ('voice' or 'text')
 * @returns {Promise<void>}
 */
async function toggleMode(newMode) {
    const wasConnected = websocket && websocket.readyState === WebSocket.OPEN || orchestratorConnected;
    
    if (wasConnected) {
        disconnect(); // Clean up current connection
    }
    
    currentMode = newMode;
    
    // Update radio button state
    if (newMode === 'voice') {
        document.getElementById('voiceModeRadio').checked = true;
        document.getElementById('textModeRadio').checked = false;
    } else {
        document.getElementById('voiceModeRadio').checked = false;
        document.getElementById('textModeRadio').checked = true;
    }
    
    if (wasConnected) {
        // Reconnect in new mode using existing session
        if (newMode === 'voice') {
            await connectVoiceMode();
        } else {
            await connectTextMode();
        }
    }
}

// WebSocket connection - routes to appropriate mode
function connect() {
    if (currentMode === 'voice') {
        connectVoiceMode();
    } else {
        connectTextMode();
    }
}

function disconnect() {
    stopRecording();
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    orchestratorConnected = false;
    connectBtn.disabled = false;
    disconnectBtn.disabled = true;
    muteBtn.disabled = true;
    sendTextBtn.disabled = true;
    updateStatus('disconnected');
}

// Audio recording - continuous streaming for bi-directional conversation
// Uses Web Audio API to convert to Linear PCM (required by Nova Sonic)
async function startRecording() {
    try {
        audioStream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true
            }
        });
        
        // Create AudioContext for PCM conversion
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000
        });
        
        const source = audioContext.createMediaStreamSource(audioStream);
        
        // Create ScriptProcessorNode to process audio in chunks
        // Buffer size: 4096 samples = ~256ms at 16kHz (good for real-time streaming)
        scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
        
        scriptProcessor.onaudioprocess = (event) => {
            if (isMuted) return;
            
            const inputBuffer = event.inputBuffer;
            const inputData = inputBuffer.getChannelData(0); // Get mono channel
            
            // Convert Float32Array to Int16Array (Linear PCM)
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                // Clamp to [-1, 1] and convert to 16-bit integer
                const s = Math.max(-1, Math.min(1, inputData[i]));
                pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            
            // Convert Int16Array to base64
            const base64PCM = arrayBufferToBase64(pcmData.buffer);
            sendAudio(base64PCM);
        };
        
        // Connect source to processor to output
        source.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);
        
        addMessage('System', '🎤 Microphone active - speak naturally', 'agent');
        
    } catch (error) {
        console.error('Error accessing microphone:', error);
        addMessage('Error', 'Could not access microphone', 'error');
    }
}

// Helper function to convert ArrayBuffer to base64
function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function stopRecording() {
    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
        audioStream = null;
    }
}

// Toggle mute/unmute
function toggleMute() {
    isMuted = !isMuted;
    if (isMuted) {
        muteBtn.textContent = '🔇 Muted';
        muteBtn.style.background = '#dc3545';
        addMessage('System', 'Microphone muted', 'agent');
        updateInputModeIndicator('text');  // When muted, primarily text mode
    } else {
        muteBtn.textContent = '🔊 Unmuted';
        muteBtn.style.background = '#28a745';
        addMessage('System', 'Microphone unmuted', 'agent');
        updateInputModeIndicator('mixed');  // When unmuted, mixed mode
    }
}

// Send data
function sendAudio(base64PCM) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        const message = {
            audio: base64PCM,
            sample_rate: 16000,
            format: 'pcm',  // Linear PCM (required by Nova Sonic)
            channels: 1
        };
        websocket.send(JSON.stringify(message));
    } else {
        console.warn('WebSocket not open, cannot send audio');
    }
}

/**
 * Send a text message to the orchestrator agent and display the response.
 * 
 * Sends a POST request to the orchestrator's /api/chat endpoint with the
 * message and current session_id. The response is displayed in the chat UI.
 * 
 * @async
 * @param {string} message - The text message to send to the orchestrator
 * @returns {Promise<void>}
 * @throws {Error} If the request fails or authentication is invalid
 */
async function sendTextToOrchestrator(message) {
    if (!authToken) {
        addMessage('Error', 'Please login first', 'error');
        return;
    }
    
    if (!currentSessionId) {
        addMessage('Error', 'Session not created. Please connect first.', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${ORCHESTRATOR_BASE}/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}` // Use header for security (works through proxies)
            },
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId
            })
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to send message: ${errorText}`);
        }
        
        const data = await response.json();
        addMessage('Agent', data.response, 'agent');
    } catch (error) {
        console.error('Error sending text to orchestrator:', error);
        addMessage('Error', `Failed to send message: ${error.message}`, 'error');
    }
}

function sendText() {
    const text = textInput.value.trim();
    if (!text) {
        return;  // Don't send empty messages
    }
    
    // Route based on current mode
    if (currentMode === 'text') {
        // Send to orchestrator via HTTP
        addMessage('User', text, 'user');
        textInput.value = '';
        sendTextToOrchestrator(text);
    } else {
        // Send to voice agent via WebSocket (existing behavior)
        if (!websocket || websocket.readyState !== WebSocket.OPEN) {
            addMessage('Error', 'WebSocket not connected. Please connect first.', 'error');
            return;
        }
        
        try {
            // Pause audio recording temporarily to avoid interference
            const wasMuted = isMuted;
            isMuted = true;
            lastInputWasText = true;
            
            // Update mode indicator
            updateInputModeIndicator('text');
            
            // Send text message
            websocket.send(JSON.stringify({
                text: text,
                input_type: 'text'  // Explicitly mark as text input
            }));
            
            addMessage('User', text, 'user');
            textInput.value = '';
            
            // Resume audio after a brief delay (allow text to be processed)
            setTimeout(() => {
                isMuted = wasMuted;
                // Update mode indicator back to voice or mixed
                if (!wasMuted) {
                    updateInputModeIndicator('mixed');
                } else {
                    updateInputModeIndicator('voice');
                }
            }, 500);
        } catch (error) {
            console.error('Error sending text message:', error);
            addMessage('Error', 'Failed to send text message. Please try again.', 'error');
            // Reset mute state on error
            isMuted = false;
            updateInputModeIndicator('mixed');
        }
    }
}

// Add Enter key support for text input
if (textInput) {
    textInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendText();
        }
    });
}

// Handle responses
function handleAgentResponse(data) {
    if (data.type === 'audio') {
        // Queue audio response (PCM format) for sequential playback
        const sampleRate = data.sample_rate || 16000; // Use the actual rate from server
        queueAudio(data.data, sampleRate);
        // Don't add message for every audio chunk to avoid spam
        // addMessage('Agent', '🔊 [Audio Response]', 'agent');
    } else if (data.type === 'transcript') {
        // Transcript can be from user or assistant - use role to determine
        const role = data.role || 'assistant';
        const messageText = data.data;
        
        // Avoid duplicate messages by checking if this is the same as the last message
        if (role === 'user') {
            if (lastUserMessage !== messageText) {
                addMessage('User', messageText, 'user');
                lastUserMessage = messageText;
            }
        } else {
            // Assistant transcript
            if (lastAgentMessage !== messageText) {
                addMessage('Agent', messageText, 'agent');
                lastAgentMessage = messageText;
                // Update mode indicator if this is a text response
                if (lastInputWasText) {
                    updateInputModeIndicator('text');
                    lastInputWasText = false;  // Reset after response
                }
            }
        }
    } else if (data.type === 'text') {
        // Agent's text response - display as Agent message
        // Avoid duplicates
        if (lastAgentMessage !== data.data) {
            addMessage('Agent', data.data, 'agent');
            lastAgentMessage = data.data;
        }
    } else if (data.type === 'response_start') {
        // Suppress "Agent is responding..." message for cleaner UI
    } else if (data.type === 'response_complete') {
        // Suppress "Agent finished responding" message for cleaner UI
    } else if (data.type === 'tool_use') {
        // Suppress tool use messages for cleaner UI
    } else if (data.type === 'connection_start') {
        // Suppress "Agent connection established" message (already have "Connected to voice agent")
    } else if (data.type === 'event') {
        // Debug event - silently ignore in production
    } else if (data.type === 'error') {
        addMessage('Error', data.message, 'error');
    } else {
        // Unknown response type - log at debug level if needed
        addMessage('System', `Unknown response: ${data.type}`, 'agent');
    }
}

// Initialize audio context once
function initAudioContext() {
    if (!audioContext || audioContext.state === 'closed') {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioContext;
}

// Queue audio chunks for sequential playback
function queueAudio(base64PCM, sampleRate = 16000) {
    audioQueue.push({ base64PCM, sampleRate });
    if (!isPlayingAudio) {
        processAudioQueue();
    }
}

// Process audio queue sequentially
async function processAudioQueue() {
    if (audioQueue.length === 0) {
        isPlayingAudio = false;
        return;
    }
    
    isPlayingAudio = true;
    const { base64PCM, sampleRate } = audioQueue.shift();
    
    try {
        await playAudioChunk(base64PCM, sampleRate);
        // Process next chunk after current one finishes
        processAudioQueue();
    } catch (err) {
        console.error('Error processing audio queue:', err);
        isPlayingAudio = false;
    }
}

// Play a single audio chunk
async function playAudioChunk(base64PCM, sampleRate = 16000) {
    return new Promise((resolve, reject) => {
        try {
            const context = initAudioContext();
            const contextSampleRate = context.sampleRate;
            
            // Decode base64 PCM data
            const binaryString = atob(base64PCM);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            
            // Convert bytes to Int16Array (16-bit PCM, little-endian)
            const sampleCount = bytes.length / 2;
            const pcmData = new Int16Array(sampleCount);
            const dataView = new DataView(bytes.buffer);
            
            for (let i = 0; i < sampleCount; i++) {
                // Read as little-endian 16-bit signed integer
                pcmData[i] = dataView.getInt16(i * 2, true);
            }
            
            // Convert Int16Array to Float32Array for Web Audio API
            const float32Data = new Float32Array(pcmData.length);
            for (let i = 0; i < pcmData.length; i++) {
                // Convert from 16-bit integer (-32768 to 32767) to float (-1.0 to 1.0)
                float32Data[i] = Math.max(-1, Math.min(1, pcmData[i] / 32768.0));
            }
            
            // Resample if needed
            let finalData = float32Data;
            let finalSampleRate = sampleRate;
            
            if (contextSampleRate !== sampleRate) {
                // Resample using linear interpolation
                const ratio = contextSampleRate / sampleRate;
                const newLength = Math.round(float32Data.length * ratio);
                finalData = new Float32Array(newLength);
                
                for (let i = 0; i < newLength; i++) {
                    const srcIndex = i / ratio;
                    const srcIndexFloor = Math.floor(srcIndex);
                    const srcIndexCeil = Math.min(srcIndexFloor + 1, float32Data.length - 1);
                    const fraction = srcIndex - srcIndexFloor;
                    
                    // Linear interpolation
                    finalData[i] = float32Data[srcIndexFloor] * (1 - fraction) + float32Data[srcIndexCeil] * fraction;
                }
                finalSampleRate = contextSampleRate;
            }
            
            // Create audio buffer
            const audioBuffer = context.createBuffer(1, finalData.length, finalSampleRate);
            audioBuffer.getChannelData(0).set(finalData);
            
            const source = context.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(context.destination);
            
            // Resolve when playback finishes
            source.onended = () => {
                resolve();
            };
            
            source.start();
        } catch (err) {
            console.error('Error playing audio chunk:', err);
            reject(err);
        }
    });
}

// UI helpers
function updateStatus(status) {
    statusEl.className = `status ${status}`;
    const modeText = currentMode === 'voice' ? ' (Voice Mode)' : ' (Text Mode)';
    statusEl.textContent = `Status: ${status.charAt(0).toUpperCase() + status.slice(1)}${modeText}`;
}

function updateInputModeIndicator(mode) {
    const indicator = document.getElementById('inputModeIndicator');
    if (!indicator) return;
    
    // Use currentMode if mode is not explicitly provided
    const displayMode = mode || currentMode;
    
    if (displayMode === 'text') {
        indicator.textContent = '⌨️ Text Mode';
        indicator.style.background = '#fff3e0';
    } else if (displayMode === 'voice') {
        indicator.textContent = '🎤 Voice Mode';
        indicator.style.background = '#e3f2fd';
    } else {
        indicator.textContent = '🎤⌨️ Mixed Mode';
        indicator.style.background = '#f3e5f5';
    }
}

function addMessage(sender, text, type) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.innerHTML = `<strong>${sender}:</strong> ${text}`;
    messagesEl.appendChild(messageDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Allow Enter key to send text
textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendText();
    }
});

// Allow Enter key in memory query
document.getElementById('memoryQuery').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        queryMemories();
    }
});

// Allow Enter key in diagnostic session ID
document.getElementById('diagnosticSessionId').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        runDiagnostics();
    }
});

// Diagnostic functions
let lastDiagnosticData = null;

async function runDiagnostics() {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    const sessionId = document.getElementById('diagnosticSessionId').value.trim();
    const resultsDiv = document.getElementById('diagnosticsResults');
    resultsDiv.innerHTML = '<p class="loading">Running diagnostics...</p>';
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/diagnose`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                session_id: sessionId || null
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            lastDiagnosticData = data;
            displayDiagnostics(data);
            document.getElementById('exportDiagnosticsBtn').style.display = 'inline-block';
        } else {
            const errorText = await response.text();
            resultsDiv.innerHTML = `<p style="color: red;">Error running diagnostics: ${errorText}</p>`;
        }
    } catch (error) {
        console.error('Error running diagnostics:', error);
        resultsDiv.innerHTML = `<p style="color: red;">Error running diagnostics: ${error.message}</p>`;
    }
}

function displayDiagnostics(data) {
    const resultsDiv = document.getElementById('diagnosticsResults');
    let html = '<div style="margin-bottom: 20px;">';
    html += `<h4>Diagnostic Summary</h4>`;
    html += `<p><strong>User ID:</strong> ${data.user_id} (sanitized: ${data.sanitized_user_id})</p>`;
    html += `<p><strong>Memory ID:</strong> ${data.memory_id}</p>`;
    html += `<p><strong>Region:</strong> ${data.region}</p>`;
    if (data.session_id) {
        html += `<p><strong>Session ID:</strong> ${data.session_id}</p>`;
    }
    html += `<p><strong>Total Records Found:</strong> ${data.total_records || 0}</p>`;
    html += '</div>';
    
    // Display each check
    const checks = data.checks || {};
    
    // Check 1: Parent namespace
    if (checks.parent_namespace) {
        const check = checks.parent_namespace;
        html += createDiagnosticCheckHTML('Check 1: Parent Namespace', check, `/summaries/${data.sanitized_user_id}`);
    }
    
    // Check 2: Exact session namespace
    if (checks.exact_namespace) {
        const check = checks.exact_namespace;
        html += createDiagnosticCheckHTML('Check 2: Exact Session Namespace', check, check.namespace);
    }
    
    // Check 3: Semantic namespace
    if (checks.semantic_namespace) {
        const check = checks.semantic_namespace;
        html += createDiagnosticCheckHTML('Check 3: Semantic Namespace', check, `/semantic/${data.sanitized_user_id}`);
    }
    
    // Check 4: Preferences namespace
    if (checks.preferences_namespace) {
        const check = checks.preferences_namespace;
        html += createDiagnosticCheckHTML('Check 4: Preferences Namespace', check, `/preferences/${data.sanitized_user_id}`);
    }
    
    resultsDiv.innerHTML = html;
}

function createDiagnosticCheckHTML(title, check, namespace) {
    let html = `<div class="diagnostic-check ${check.success ? 'success' : 'error'}">`;
    html += `<h5 style="margin-top: 0;">${title}</h5>`;
    html += `<p><strong>Namespace:</strong> ${check.namespace || namespace}</p>`;
    
    if (check.success) {
        html += `<p style="color: #28a745;"><strong>✅ Success:</strong> Found ${check.record_count || 0} record(s)</p>`;
        
        if (check.records && check.records.length > 0) {
            html += `<button onclick="toggleExpandable('${title.replace(/\s+/g, '_')}_records')" style="background: #6c757d; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; margin-top: 10px;">View Records</button>`;
            html += `<div id="${title.replace(/\s+/g, '_')}_records" class="expandable-content">`;
            check.records.forEach((record, index) => {
                html += `<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 3px;">`;
                html += `<p><strong>Record ${index + 1}:</strong></p>`;
                html += `<p style="font-size: 12px; color: #666;">Record ID: ${record.memoryRecordId || record.recordId || 'N/A'}</p>`;
                const content = record.content || {};
                const text = content.text || '';
                if (text) {
                    const preview = text.length > 200 ? text.substring(0, 200) + '...' : text;
                    html += `<p style="white-space: pre-wrap; font-size: 12px;">${preview}</p>`;
                }
                html += `</div>`;
            });
            html += `</div>`;
        }
    } else {
        html += `<p style="color: #dc3545;"><strong>❌ Error:</strong> ${check.error || 'Unknown error'}</p>`;
        if (check.error_code) {
            html += `<p style="font-size: 12px; color: #666;">Error Code: ${check.error_code}</p>`;
        }
    }
    
    html += `</div>`;
    return html;
}

function toggleExpandable(id) {
    const element = document.getElementById(id);
    if (element) {
        element.classList.toggle('show');
    }
}

function exportDiagnostics() {
    if (!lastDiagnosticData) {
        alert('No diagnostic data to export. Please run diagnostics first.');
        return;
    }
    
    const dataStr = JSON.stringify(lastDiagnosticData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `memory-diagnostics-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
}

// Initialize authentication and mode on page load
window.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    // Initialize mode indicator
    updateInputModeIndicator(currentMode);
    // Set radio button to match current mode
    document.getElementById('voiceModeRadio').checked = (currentMode === 'voice');
    document.getElementById('textModeRadio').checked = (currentMode === 'text');
});
