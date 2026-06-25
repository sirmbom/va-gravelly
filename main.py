import os
import re
import types
import asyncio
import uuid
import webbrowser
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from vision_agents.core import Agent, AgentLauncher, User, Runner
from vision_agents.plugins import getstream, gemini

load_dotenv()

# Monkey-patch EventManager to resolve NoneType startswith AttributeError on Render
from vision_agents.core.events.manager import EventManager
def safe_register_events_from_module(self, module, prefix="", ignore_not_compatible=True):
    for name, class_ in module.__dict__.items():
        if name.endswith("Event"):
            evt_type = getattr(class_, "type", "")
            if evt_type is None:
                evt_type = ""
            if not prefix or evt_type.startswith(prefix):
                self.register(class_, ignore_not_compatible=ignore_not_compatible)
                self._modules.setdefault(module.__name__, []).append(class_)
EventManager.register_events_from_module = safe_register_events_from_module


# Regex for common filler words in English/French
FILLER_REGEX = re.compile(r'\b(uh|um|like|you know|euh|donc|ah)\b', re.IGNORECASE)

async def create_agent(**kwargs) -> Agent:
    """
    Instantiate the AI coach agent using Gemini Realtime (models/gemini-3.1-flash-live-preview).
    """
    from google import genai
    client = genai.Client(http_options={"api_version": "v1beta"})
    
    llm = gemini.Realtime(
        model="models/gemini-3.1-flash-live-preview",
        client=client
    )
    # Pop affective dialog to prevent 1007 WebRTC errors
    llm._base_config.pop("enable_affective_dialog", None)
    
    # Patch transcription emitters to intercept user speech & coach responses in real-time
    original_emit_user_transcription = llm._emit_user_speech_transcription
    original_emit_agent_transcription = llm._emit_agent_speech_transcription
    
    llm._agent_ref = None # Will be set after agent initialization
    
    def patched_emit_user_transcription(self, text: str, *, mode: str):
        original_emit_user_transcription(text, mode=mode)
        agent_obj = getattr(self, "_agent_ref", None)
        if not agent_obj:
            return
            
        if mode == "final":
            agent_obj.user_transcripts.append(text)
            
            # Scan for filler words
            matches = FILLER_REGEX.findall(text)
            if matches:
                agent_obj.filler_word_count += len(matches)
                print(f"\n>>> [FILLER WORD DETECTED]: {matches} in user utterance: '{text}' <<<\n")
                
            # Words Per Minute calculation
            words = len(text.split())
            agent_obj.total_words += words
            if agent_obj.start_time is None:
                agent_obj.start_time = asyncio.get_event_loop().time()
            
            duration = asyncio.get_event_loop().time() - agent_obj.start_time
            if duration > 1.0:
                agent_obj.wpm = (agent_obj.total_words / duration) * 60.0

    def patched_emit_agent_transcription(self, text: str, *, mode: str):
        original_emit_agent_transcription(text, mode=mode)
        agent_obj = getattr(self, "_agent_ref", None)
        if not agent_obj:
            return
            
        if mode == "final":
            agent_obj.agent_transcripts.append(text)
            print(f"\n>>> [COACH NOTE]: {text} <<<\n")
            
    llm._emit_user_speech_transcription = types.MethodType(patched_emit_user_transcription, llm)
    llm._emit_agent_speech_transcription = types.MethodType(patched_emit_agent_transcription, llm)
    
    agent = Agent(
        edge=getstream.Edge(),
        agent_user=User(name="Coach", id="agent"),
        instructions=(
            "You are a real-time pitch coaching assistant. Take notes of any filler words "
            "(e.g. 'um', 'uh', 'like', 'you know') that the user uses in their speech."
        ),
        llm=llm,
    )
    
    # Initialize custom coach tracking attributes
    agent.user_transcripts = []
    agent.agent_transcripts = []
    agent.filler_word_count = 0
    agent.total_words = 0
    agent.start_time = None
    agent.wpm = 0.0
    
    # Bind the agent reference back to the patched LLM
    llm._agent_ref = agent
    
    # Register the stop session tool
    @agent.llm.register_function(description="Stops the current live session when the user finishes their pitch.")
    async def stop_session() -> dict:
        print("[Agent] stop_session triggered. Closing agent.")
        await agent.close()
        return {"result": "Stopping"}
        
    return agent

async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs) -> None:
    call = await agent.create_call(call_type, call_id)
    async with agent.join(call):
        print(f"Agent joined call '{call_id}' as WebRTC participant. Listening for speech...")
        await agent.finish()

async def get_human_join_url(call_id: str) -> str:
    """
    Generate the GetStream web client demo URL for the human user.
    """
    edge = getstream.Edge()
    await edge.authenticate(User(id="user-demo-agent", name="Human User"))
    call = await edge.create_call(call_id)
    url = await edge.open_demo(call)
    await edge.close()
    return url

# Initialize Launcher and Runner
launcher = AgentLauncher(create_agent=create_agent, join_call=join_call)
runner = Runner(launcher=launcher)
app = runner.fast_api

@app.get("/get-join-url")
async def join_url_endpoint(call_id: str):
    try:
        url = await get_human_join_url(call_id)
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/custom-session-info")
async def custom_session_info(call_id: str):
    active_session = None
    for s in launcher._sessions.values():
        if s.call_id == call_id:
            active_session = s
            break
            
    if active_session is None:
        return {
            "active": False,
            "session_id": None,
            "filler_words": 0,
            "wpm": 0,
            "user_transcripts": [],
            "agent_transcripts": []
        }
        
    return {
        "active": True,
        "session_id": active_session.id,
        "filler_words": getattr(active_session.agent, "filler_word_count", 0),
        "wpm": round(getattr(active_session.agent, "wpm", 0.0), 1),
        "user_transcripts": getattr(active_session.agent, "user_transcripts", []),
        "agent_transcripts": getattr(active_session.agent, "agent_transcripts", [])
    }

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    dashboard_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Project Gravelly | Real-time AI Pitch Coach</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: #0E0E11;
                --surface: #16161A;
                --panel: #1E1E24;
                --border: rgba(255, 255, 255, 0.07);
                --text-ghost: #F4F4F5;
                --text-silver: #C4C4CC;
                --text-muted: #6B7280;
                --amber: #F59E0B;
                --danger: #EF4444;
                --success: #22C55E;
            }

            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                background-color: var(--bg);
                color: var(--text-silver);
                font-family: 'Outfit', sans-serif;
                height: 100vh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            header {
                height: 70px;
                border-bottom: 1px solid var(--border);
                padding: 0 30px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                background-color: rgba(22, 22, 26, 0.5);
                backdrop-filter: blur(10px);
                z-index: 10;
            }

            .logo-container {
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .logo-badge {
                width: 32px;
                height: 32px;
                border-radius: 8px;
                background-color: var(--amber);
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 900;
                color: var(--bg);
                font-size: 14px;
            }

            .logo-text {
                font-size: 16px;
                font-weight: 700;
                color: var(--text-ghost);
                letter-spacing: 0.1em;
            }

            .status-container {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 14px;
                background-color: var(--surface);
                border: 1px solid var(--border);
                border-radius: 20px;
            }

            .status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background-color: var(--text-muted);
            }

            .status-dot.active {
                background-color: var(--amber);
                box-shadow: 0 0 10px var(--amber);
                animation: pulse 1.5s infinite;
            }

            .status-text {
                font-family: 'JetBrains Mono', monospace;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            main {
                flex-grow: 1;
                display: grid;
                grid-template-columns: 350px 1fr;
                gap: 20px;
                padding: 24px;
                overflow: hidden;
            }

            .sidebar {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }

            .card {
                background-color: var(--surface);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 24px;
                display: flex;
                flex-direction: column;
            }

            .card-title {
                font-size: 14px;
                color: var(--text-ghost);
                font-weight: 700;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .input-group {
                margin-bottom: 20px;
            }

            .input-label {
                font-size: 11px;
                text-transform: uppercase;
                font-family: 'JetBrains Mono', monospace;
                color: var(--text-muted);
                margin-bottom: 8px;
                display: block;
            }

            .input-wrapper {
                display: flex;
                gap: 8px;
            }

            input {
                flex-grow: 1;
                background-color: var(--panel);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 10px 14px;
                color: var(--text-ghost);
                font-family: 'JetBrains Mono', monospace;
                font-size: 14px;
                outline: none;
            }

            input:focus {
                border-color: var(--amber);
            }

            .btn-refresh {
                background-color: var(--panel);
                border: 1px solid var(--border);
                color: var(--text-ghost);
                border-radius: 8px;
                width: 40px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background-color 0.2s;
            }

            .btn-refresh:hover {
                background-color: var(--border);
            }

            .action-btn {
                width: 100%;
                padding: 14px;
                border-radius: 12px;
                font-weight: 700;
                font-size: 14px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                transition: all 0.2s;
                margin-bottom: 12px;
                text-decoration: none;
            }

            .btn-primary {
                background-color: var(--amber);
                color: var(--bg);
                border: none;
            }

            .btn-primary:hover {
                opacity: 0.9;
                transform: translateY(-1px);
            }

            .btn-secondary {
                background-color: var(--panel);
                color: var(--text-ghost);
                border: 1px solid var(--border);
            }

            .btn-secondary:hover:not(:disabled) {
                background-color: var(--border);
                transform: translateY(-1px);
            }

            .btn-secondary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .btn-danger {
                background-color: transparent;
                color: var(--danger);
                border: 1px solid rgba(239, 68, 68, 0.3);
            }

            .btn-danger:hover:not(:disabled) {
                background-color: rgba(239, 68, 68, 0.1);
                transform: translateY(-1px);
            }

            .btn-danger:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .content-area {
                display: grid;
                grid-template-rows: auto 1fr;
                gap: 20px;
                overflow: hidden;
            }

            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
            }

            .metric-card {
                position: relative;
                overflow: hidden;
            }

            .metric-abbr {
                position: absolute;
                top: 8px;
                right: 12px;
                font-family: 'JetBrains Mono', monospace;
                font-size: 40px;
                font-weight: 900;
                opacity: 0.03;
                pointer-events: none;
            }

            .metric-value {
                font-family: 'JetBrains Mono', monospace;
                font-size: 52px;
                font-weight: 700;
                color: var(--text-ghost);
                line-height: 1;
                margin-top: 5px;
            }

            .metric-help {
                font-family: 'JetBrains Mono', monospace;
                font-size: 9px;
                color: var(--text-muted);
                text-transform: uppercase;
                margin-top: 8px;
            }

            .transcript-container {
                display: flex;
                flex-direction: column;
                height: 100%;
                overflow: hidden;
            }

            .transcript-logs {
                flex-grow: 1;
                overflow-y: auto;
                padding-right: 8px;
                display: flex;
                flex-direction: column;
                gap: 16px;
            }

            .transcript-logs::-webkit-scrollbar {
                width: 4px;
            }

            .transcript-logs::-webkit-scrollbar-track {
                background: transparent;
            }

            .transcript-logs::-webkit-scrollbar-thumb {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 4px;
            }

            .transcript-logs::-webkit-scrollbar-thumb:hover {
                background: rgba(255, 255, 255, 0.1);
            }

            .bubble {
                padding: 16px;
                border-radius: 12px;
                border: 1px solid var(--border);
                background-color: rgba(30, 30, 36, 0.3);
                animation: fadeIn 0.3s ease-out;
            }

            .bubble.coach {
                border-left: 3px solid var(--amber);
                background-color: rgba(245, 158, 11, 0.03);
            }

            .bubble.user {
                border-left: 3px solid var(--text-muted);
            }

            .bubble-meta {
                font-family: 'JetBrains Mono', monospace;
                font-size: 9px;
                color: var(--text-muted);
                text-transform: uppercase;
                margin-bottom: 8px;
                letter-spacing: 0.05em;
            }

            .bubble-text {
                font-size: 14px;
                color: var(--text-ghost);
                line-height: 1.5;
            }

            .placeholder-logs {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-muted);
                gap: 12px;
            }

            .placeholder-logs svg {
                opacity: 0.2;
            }

            @keyframes pulse {
                0% { opacity: 0.5; }
                50% { opacity: 1; }
                100% { opacity: 0.5; }
            }

            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(8px); }
                to { opacity: 1; transform: translateY(0); }
            }
        </style>
    </head>
    <body>
        <header>
            <div class="logo-container">
                <div class="logo-badge">GR</div>
                <div class="logo-text">GRAVELLY CONTROL PANEL</div>
            </div>
            <div class="status-container">
                <div class="status-dot" id="status-dot"></div>
                <span class="status-text" id="status-text">OFFLINE</span>
            </div>
        </header>

        <main>
            <div class="sidebar">
                <div class="card">
                    <div class="card-title">Session Configuration</div>
                    <div class="input-group">
                        <label class="input-label">Call Room ID</label>
                        <div class="input-wrapper">
                            <input type="text" id="call-id-input" placeholder="Room ID">
                            <button class="btn-refresh" onclick="generateRandomCallId()" title="Generate Random ID">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                            </button>
                        </div>
                    </div>

                    <div style="margin-top: auto; display: flex; flex-direction: column;">
                        <button class="action-btn btn-primary" onclick="joinCallAsHuman()">
                            1. Join Call (as Human)
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3"/></svg>
                        </button>
                        <button class="action-btn btn-secondary" id="btn-add-agent" onclick="addAgentToCall()" disabled>
                            2. Add AI Agent to Call
                        </button>
                        <button class="action-btn btn-danger" id="btn-remove-agent" onclick="removeAgentFromCall()" disabled>
                            3. Remove AI Agent
                        </button>
                    </div>
                </div>

                <div class="card" style="flex-grow: 1;">
                    <div class="card-title">Call Instructions</div>
                    <div style="font-size: 13px; line-height: 1.6; color: var(--text-silver); display: flex; flex-direction: column; gap: 12px;">
                        <p><strong>Step 1:</strong> Type a Call Room ID or generate one, then join the call. GetStream will open in a new tab.</p>
                        <p><strong>Step 2:</strong> Once inside the Stream Call room, return here and add the AI Agent. It will connect dynamically.</p>
                        <p><strong>Step 3:</strong> Start pitching! The metrics panel and notes on the right will update in real-time as you speak.</p>
                    </div>
                </div>
            </div>

            <div class="content-area">
                <div class="metrics-grid">
                    <div class="card metric-card">
                        <div class="metric-abbr">WPM</div>
                        <label class="input-label">Pace (WPM)</label>
                        <div class="metric-value" id="metric-wpm">0</div>
                        <div class="metric-help">Target: 130 - 160 WPM</div>
                    </div>
                    <div class="card metric-card">
                        <div class="metric-abbr">FLR</div>
                        <label class="input-label">Filler Words</label>
                        <div class="metric-value" id="metric-fillers">0</div>
                        <div class="metric-help">Target: 0 per session</div>
                    </div>
                </div>

                <div class="card transcript-container">
                    <div class="card-title">Real-time Coaching Feed</div>
                    <div class="transcript-logs" id="transcript-logs">
                        <div class="placeholder-logs" id="placeholder-logs">
                            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
                            <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em;">Waiting for call to begin...</span>
                        </div>
                    </div>
                </div>
            </div>
        </main>

        <script>
            let currentCallId = "";
            let currentSessionId = "";
            let pollInterval = null;

            function generateRandomCallId() {
                const randomId = "call-" + Math.random().toString(36).substring(2, 10);
                document.getElementById("call-id-input").value = randomId;
            }

            // Generate initial random Call ID on load
            generateRandomCallId();

            function updateStatus(status) {
                const dot = document.getElementById("status-dot");
                const text = document.getElementById("status-text");
                const btnAdd = document.getElementById("btn-add-agent");
                const btnRemove = document.getElementById("btn-remove-agent");

                if (status === "offline") {
                    dot.className = "status-dot";
                    text.innerText = "OFFLINE";
                    btnRemove.disabled = true;
                } else if (status === "joining") {
                    dot.className = "status-dot active";
                    text.innerText = "AGENT JOINING";
                    btnAdd.disabled = true;
                    btnRemove.disabled = true;
                } else if (status === "active") {
                    dot.className = "status-dot active";
                    text.innerText = "AI COACH ACTIVE";
                    btnAdd.disabled = true;
                    btnRemove.disabled = false;
                }
            }

            async function joinCallAsHuman() {
                const callId = document.getElementById("call-id-input").value.trim();
                if (!callId) {
                    alert("Please enter or generate a Call Room ID.");
                    return;
                }
                currentCallId = callId;
                
                try {
                    const response = await fetch(`/get-join-url?call_id=${callId}`);
                    const data = await response.json();
                    if (data.url) {
                        window.open(data.url, '_blank');
                        document.getElementById("btn-add-agent").disabled = false;
                    } else {
                        alert("Error generating join link.");
                    }
                } catch (e) {
                    console.error(e);
                    alert("Failed to connect to the backend.");
                }
            }

            async function addAgentToCall() {
                if (!currentCallId) return;
                updateStatus("joining");

                try {
                    const response = await fetch(`/calls/${currentCallId}/sessions`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ call_type: "default" })
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        currentSessionId = data.session_id;
                        updateStatus("active");
                        startPolling();
                    } else {
                        alert("Failed to spawn the agent.");
                        updateStatus("offline");
                        document.getElementById("btn-add-agent").disabled = false;
                    }
                } catch (e) {
                    console.error(e);
                    alert("Error communicating with agent server.");
                    updateStatus("offline");
                    document.getElementById("btn-add-agent").disabled = false;
                }
            }

            async function removeAgentFromCall() {
                if (!currentCallId || !currentSessionId) return;
                
                try {
                    const response = await fetch(`/calls/${currentCallId}/sessions/${currentSessionId}`, {
                        method: 'DELETE'
                    });
                    if (response.ok) {
                        stopPolling();
                        updateStatus("offline");
                        document.getElementById("btn-add-agent").disabled = false;
                        currentSessionId = "";
                    } else {
                        alert("Failed to close agent session.");
                    }
                } catch (e) {
                    console.error(e);
                }
            }

            function startPolling() {
                if (pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(pollSessionInfo, 1000);
            }

            function stopPolling() {
                if (pollInterval) {
                    clearInterval(pollInterval);
                    pollInterval = null;
                }
            }

            async function pollSessionInfo() {
                if (!currentCallId) return;
                
                try {
                    const response = await fetch(`/custom-session-info?call_id=${currentCallId}`);
                    const data = await response.json();
                    
                    if (!data.active && currentSessionId) {
                        // Session has ended remotely or agent left
                        stopPolling();
                        updateStatus("offline");
                        document.getElementById("btn-add-agent").disabled = false;
                        currentSessionId = "";
                        return;
                    }

                    // Update metrics
                    document.getElementById("metric-wpm").innerText = data.wpm;
                    document.getElementById("metric-fillers").innerText = data.filler_words;

                    // Update Logs
                    const logs = document.getElementById("transcript-logs");
                    const placeholder = document.getElementById("placeholder-logs");

                    if (data.user_transcripts.length === 0 && data.agent_transcripts.length === 0) {
                        if (placeholder) placeholder.style.display = "flex";
                        return;
                    }

                    if (placeholder) placeholder.style.display = "none";

                    // Merge and sort user + coach events based on arrival or sequence
                    // Since both are ordered lists, we can weave them or display them grouped.
                    // To keep it simple and clean, we weave them in the order of user -> coach interaction
                    let logHtml = "";
                    
                    // Display all user speech
                    const totalTurns = Math.max(data.user_transcripts.length, data.agent_transcripts.length);
                    for (let i = 0; i < totalTurns; i++) {
                        if (i < data.user_transcripts.length) {
                            logHtml += `
                                <div class="bubble user">
                                    <div class="bubble-meta">YOU (USER)</div>
                                    <div class="bubble-text">${escapeHtml(data.user_transcripts[i])}</div>
                                </div>
                            `;
                        }
                        if (i < data.agent_transcripts.length) {
                            logHtml += `
                                <div class="bubble coach">
                                    <div class="bubble-meta">COACH NOTES (AI)</div>
                                    <div class="bubble-text">${escapeHtml(data.agent_transcripts[i])}</div>
                                </div>
                            `;
                        }
                    }
                    
                    // Only update innerHTML if it has changed to avoid screen flickering
                    if (logs.innerHTML !== logHtml) {
                        logs.innerHTML = logHtml;
                        logs.scrollTop = logs.scrollHeight;
                    }
                } catch (e) {
                    console.error("Polling error:", e);
                }
            }

            function escapeHtml(text) {
                return text
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#039;");
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=dashboard_html)

if __name__ == "__main__":
    # uv run python main.py serve --port 8000
    runner.cli()