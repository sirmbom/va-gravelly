# Gravelly

Gravelly is a vision-agent-powered coaching app designed to help people improve their public speaking, presentation delivery, and job interview performance in real time. It combines speech analysis with an AI coach experience to give users live feedback on pacing, filler words, and overall clarity.

## What this project does

This project uses Gemini and Stream-based vision agents to create a live coaching experience where users can:

- practice speaking in a realistic interview or presentation flow
- receive live coaching feedback from an AI assistant
- track metrics such as filler word usage and words-per-minute
- use a simple web dashboard to start a coaching session

## Project structure

- main.py: the FastAPI app and agent orchestration logic
- pyproject.toml: Python package metadata and dependencies
- render.yaml: Render deployment configuration

## Prerequisites

Before running the app locally, make sure you have:

- Python 3.12 or newer
- access to the following API credentials:
  - GOOGLE_API_KEY
  - STREAM_API_KEY
  - STREAM_API_SECRET

## Local setup

1. Create and activate a virtual environment:

   On Windows PowerShell:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```bash
   pip install -e .
   ```

3. Create a .env file in the project root with your credentials:

   ```env
   GOOGLE_API_KEY=your_google_api_key
   STREAM_API_KEY=your_stream_api_key
   STREAM_API_SECRET=your_stream_api_secret
   ```

4. Start the app:

   ```bash
   python main.py serve --host 0.0.0.0 --port 8000
   ```

5. Open the dashboard in your browser:

   ```text
   http://127.0.0.1:8000/
   ```

## How to use the app

- Open the homepage to access the coaching dashboard.
- Start a coaching session from the interface.
- The AI assistant will listen to the user and provide live feedback, including notes about filler words and speaking pace.

## Deploying to Render

This repository includes a Render configuration in render.yaml for easy deployment.

### Steps

1. Push this repository to GitHub.
2. Create a new Web Service in Render and connect the repository.
3. Render will read render.yaml automatically.
4. Add the required environment variables in the Render dashboard:
   - GOOGLE_API_KEY
   - STREAM_API_KEY
   - STREAM_API_SECRET
5. Deploy the service.

### Render configuration summary

The current render.yaml config:

- creates a Python web service named gravelly-ai-coach
- installs dependencies with pip install .
- starts the app with:

  ```bash
  python main.py serve --host 0.0.0.0 --port $PORT
  ```

### Important note

Render will not know your secrets unless you add them manually in the service environment settings. The render.yaml file marks them as sync: false so they can be provided securely from the Render dashboard.

## Troubleshooting

If the app does not start:

- confirm your Python version is 3.12+
- verify that your .env file exists and contains the required variables
- ensure your API keys are valid and active
- check the terminal output for missing dependency or authentication errors

## License

This project is intended for demonstration and coaching use cases.
