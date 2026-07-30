import os
from dotenv import load_dotenv

# Load environmental variables early
load_dotenv()

# Apply event manager monkey patches early
from patch import patch_event_manager
patch_event_manager()

from vision_agents.core import AgentLauncher, Runner
from agent import create_agent, join_call
from web import register_routes

# Initialize Launcher and Runner
launcher = AgentLauncher(create_agent=create_agent, join_call=join_call)
runner = Runner(launcher=launcher)
app = runner.fast_api

# Register all web routing and endpoints
register_routes(app, launcher)

if __name__ == "__main__":
    # uv run python main.py serve --port 8000
    runner.cli()