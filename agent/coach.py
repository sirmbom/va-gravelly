import re
import types
import asyncio
from google import genai
from vision_agents.core import Agent, User
from vision_agents.plugins import getstream, gemini

# Regex for common filler words in English/French
FILLER_REGEX = re.compile(r'\b(uh|um|like|you know|euh|donc|ah)\b', re.IGNORECASE)

async def create_agent(**kwargs) -> Agent:
    """
    Instantiate the AI coach agent using Gemini Realtime (models/gemini-3.1-flash-live-preview).
    """
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
    
    llm._agent_ref = None  # Will be set after agent initialization
    
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
