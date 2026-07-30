# Gravelly: Real-Time AI Speech Coach & Interview Prep Trainer

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=00FFCC)](https://fastapi.tiangolo.com/)
[![Google GenAI SDK](https://img.shields.io/badge/Google%20GenAI%20SDK-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://github.com/google/generative-ai-python)
[![GetStream WebRTC](https://img.shields.io/badge/GetStream%20WebRTC-0052FF?style=for-the-badge&logo=stream&logoColor=white)](https://getstream.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

> Real-time AI speech coach & interview trainer powered by Gemini Live API & GetStream WebRTC. Tracks speaking pace and filler words to deliver instant conversational feedback.

Gravelly is an innovative, vision-agent-powered coaching application designed to help professionals, speakers, and job candidates refine public speaking, presentation delivery, and interview performance in real time. By leveraging low-latency, bi-directional WebRTC audio streaming, Gravelly analyzes speech patterns to intercept filler words and track words-per-minute (WPM), giving users actionable live vocal mentoring.

---

## Interactive Trial Showcase

<div align="center">
  <a href="#" target="_blank">
    <img src="https://img.shields.io/badge/Interactive%20Trial-Local%20Setup%20Required-FF4500?style=for-the-badge&logo=google-chrome&logoColor=white" height="40" alt="Gravelly Interactive Trial" />
  </a>
</div>

### Running the Local Interactive Demo:
1. Clone the repository and configure `.env` with your `STREAM_API_KEY`, `STREAM_API_SECRET`, and `GEMINI_API_KEY`.
2. Start the server using `python main.py`.
3. Open `http://localhost:8000` in your web browser.
4. Select your coaching scenario (Interview or Pitch Presentation).
5. Click **Start Coaching Session** to initialize the low-latency WebRTC connection.

---

## Key Features

* **Bi-Directional WebRTC Audio Streaming**: Built on GetStream WebRTC edge infrastructure for sub-second vocal interaction.
* **Live Speech Analytics**: Real-time monkey-patching of transcription emitters tracks WPM and detects filler words (`uh`, `um`, `like`, `you know`) via regex.
* **Dynamic Web Dashboard**: Modern dark-themed UI featuring real-time polling to `/custom-session-info` for live metrics rendering.
* **Customizable Personas**: Adaptive coaching system instructions tailored for public speaking or technical job interview prep.

---

## Architecture Overview

```
[ User Browser / WebRTC Client ]
            │
    (WebRTC Stream / Audio Chunks)
            │
            ▼
[ GetStream Edge Infrastructure ] ── (Server Events) ──► [ FastAPI Backend ]
                                                                 │
                                                    (Patched Speech Emitters)
                                                                 │
                                                                 ▼
                                                  [ Gemini Live WebSockets ]
```

---

## Repository Metadata & SEO Parameters

* **About Description**: Real-time AI speech coach & interview trainer powered by Gemini Live API & GetStream WebRTC. Tracks speaking pace and filler words to deliver instant conversational feedback.
* **Target Topics**: `gemini-live-api`, `webrtc`, `speech-coaching`, `fastapi`, `getstream`, `realtime-ai`, `python`, `ai-coach`.

---

## Environment Configuration

Copy `.env.example` to `.env` and configure the following:

```env
GEMINI_API_KEY=your_gemini_api_key
STREAM_API_KEY=your_stream_api_key
STREAM_API_SECRET=your_stream_api_secret
PORT=8000
```

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
