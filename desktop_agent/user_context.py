"""Stable, non-sensitive user context for local intent understanding.

Keep this concise and focused on facts that help resolve project names,
technical vocabulary, and likely intent. This is context, never permission.
"""

USER_CONTEXT = {
    "identity": [
        "The user is Muhammad Navas, an engineering student.",
        "He is pursuing a B.E. in Computer Science with an Artificial Intelligence and Machine Learning specialization at CMR Institute of Technology, Bengaluru.",
        "He is interested in AI engineering, software development, and improving his technical skills.",
    ],
    "communication": [
        "The user may speak with an Indian English accent and speech-to-text may mishear technical terms, project names, or English words.",
        "Interpret the meaning and likely intent rather than requiring perfect pronunciation or exact spelling.",
        "If a transcript is a close phonetic match for a known project, tool, or command, resolve it using this context before deciding the request is unsupported.",
        "Do not silently change the requested action when there are multiple plausible meanings; ask a short clarification instead.",
    ],
    "known_projects": [
        "AI Browser Automation Agent: a Python FastAPI backend and frontend project at D:\\Projects\\Python\\ai-browser-automation-agent; the user opens it in Google Antigravity and starts frontend and backend development servers.",
        "Desktop Agent: this local-first Windows assistant, using Ollama, Alexa wake-word detection, voice transcription, registered tools, and local memory.",
        "Nudi LLM: the user's small Kannada language model project.",
        "Notezy.online: a VTU notes-sharing platform co-founded by the user.",
        "MazeScape and DoodleRush: the user's web game projects.",
    ],
    "technical_vocabulary": [
        "The user works with Python, FastAPI, JavaScript, TypeScript, React, Next.js, Node.js, PostgreSQL, MongoDB, Docker, Kubernetes, Git, Ollama, LangChain, RAG, and machine learning.",
        "Antigravity is the user's AI coding IDE. The speech transcript may render it as 'anti gravity'.",
        "Code Autometa is the user's phrase for opening the AI Browser Automation Agent project in Antigravity and starting its frontend and backend development servers.",
        "Code Autometa may be transcribed as 'Code Automata', 'Code Automate', 'Code Auto Meta', or similar close phonetic variants.",
    ],
}


def format_user_context() -> str:
    """Render stable user context for the local model prompt."""
    return "\\n".join(
        f"{section.replace('_', ' ').title()}: " + "; ".join(items)
        for section, items in USER_CONTEXT.items()
    )
