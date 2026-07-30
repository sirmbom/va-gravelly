import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from agent.coach import get_human_join_url

# Get absolute path to the templates directory
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
DASHBOARD_PATH = os.path.join(TEMPLATE_DIR, "dashboard.html")

def get_dashboard_html() -> str:
    """
    Read and return the dashboard HTML template.
    """
    if not os.path.exists(DASHBOARD_PATH):
        raise RuntimeError(f"Dashboard template not found at {DASHBOARD_PATH}")
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        return f.read()

def register_routes(app: FastAPI, launcher):
    """
    Register the web and API routes on the FastAPI application.
    """
    
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
        try:
            html_content = get_dashboard_html()
            return HTMLResponse(content=html_content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {str(e)}")
