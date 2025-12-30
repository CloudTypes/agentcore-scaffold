let websocket = null;
let audioContext = null;
let audioStream = null;
let scriptProcessor = null;
let isMuted = false;

// Audio playback queue
let audioQueue = [];
let isPlayingAudio = false;

// Track last messages to avoid duplicates
let lastUserMessage = null;
let lastAgentMessage = null;

// Authentication state
let authToken = null;
let currentUser = null;
// Determine API base URL - handle file:// protocol for local HTML files
const getApiBase = () => {
    if (window.location.protocol === 'file:' || !window.location.origin || window.location.origin === 'null') {
        return 'http://localhost:8080';
    }
    return window.location.origin;
};
const API_BASE = getApiBase();

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

// WebSocket connection
function connect() {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    // Convert HTTP URL to WebSocket URL
    const wsProtocol = API_BASE.startsWith('https') ? 'wss:' : 'ws:';
    const wsHost = API_BASE.replace(/^https?:/, '').replace(/^\/\//, '');
    const wsUrl = `${wsProtocol}//${wsHost}/ws?token=${encodeURIComponent(authToken)}`;
    
    websocket = new WebSocket(wsUrl);
    
    websocket.onopen = async () => {
        updateStatus('connected');
        // Don't add connection message - status indicator is sufficient
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
        muteBtn.disabled = false;
        sendTextBtn.disabled = false;
        
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

function disconnect() {
    stopRecording();
    if (websocket) {
        websocket.close();
        websocket = null;
    }
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
    } else {
        muteBtn.textContent = '🔊 Unmuted';
        muteBtn.style.background = '#28a745';
        addMessage('System', 'Microphone unmuted', 'agent');
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

function sendText() {
    const text = textInput.value.trim();
    if (text && websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            text: text
        }));
        addMessage('User', text, 'user');
        textInput.value = '';
    }
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
            if (lastAgentMessage !== messageText) {
                addMessage('Agent', messageText, 'agent');
                lastAgentMessage = messageText;
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
    statusEl.textContent = `Status: ${status.charAt(0).toUpperCase() + status.slice(1)}`;
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

// Initialize authentication on page load
window.addEventListener('DOMContentLoaded', () => {
    checkAuth();
});
