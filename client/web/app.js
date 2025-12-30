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

// Memory API functions
async function queryMemories() {
    const query = document.getElementById('memoryQuery').value;
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ query, top_k: 5 })
        });
        
        if (response.ok) {
            const data = await response.json();
            const resultsDiv = document.getElementById('preferences');
            resultsDiv.innerHTML = '<h4>Search Results:</h4>';
            if (data.memories && data.memories.length > 0) {
                data.memories.forEach(mem => {
                    const memDiv = document.createElement('div');
                    memDiv.style.padding = '10px';
                    memDiv.style.margin = '5px 0';
                    memDiv.style.background = 'white';
                    memDiv.style.borderRadius = '5px';
                    memDiv.textContent = mem.content || JSON.stringify(mem);
                    resultsDiv.appendChild(memDiv);
                });
            } else {
                resultsDiv.innerHTML += '<p>No memories found.</p>';
            }
        } else {
            alert('Error querying memories');
        }
    } catch (error) {
        console.error('Error querying memories:', error);
        alert('Error querying memories');
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
                    prefDiv.textContent = pref.content || JSON.stringify(pref);
                    prefsDiv.appendChild(prefDiv);
                });
            } else {
                prefsDiv.innerHTML += '<p>No preferences found.</p>';
            }
        } else {
            alert('Error loading preferences');
        }
    } catch (error) {
        console.error('Error loading preferences:', error);
        alert('Error loading preferences');
    }
}

async function loadSessions() {
    if (!authToken) {
        alert('Please login first');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/sessions`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            const sessionsDiv = document.getElementById('sessions');
            sessionsDiv.innerHTML = '<h4>Sessions:</h4>';
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(session => {
                    const sessionDiv = document.createElement('div');
                    sessionDiv.style.padding = '10px';
                    sessionDiv.style.margin = '5px 0';
                    sessionDiv.style.background = 'white';
                    sessionDiv.style.borderRadius = '5px';
                    sessionDiv.textContent = `Session: ${session.session_id || session.id}`;
                    sessionsDiv.appendChild(sessionDiv);
                });
            } else {
                sessionsDiv.innerHTML += '<p>No sessions found.</p>';
            }
        } else {
            alert('Error loading sessions');
        }
    } catch (error) {
        console.error('Error loading sessions:', error);
        alert('Error loading sessions');
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

// Initialize authentication on page load
window.addEventListener('DOMContentLoaded', () => {
    checkAuth();
});
