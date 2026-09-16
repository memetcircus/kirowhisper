"""Voice simulation — a rules-compliant simulated Alexa+ experience.

The backend (MCP + Crew + Bedrock) is entirely real; only the Alexa+ interaction
layer is simulated here as a web UI (browser Web Speech API for STT + TTS) talking
to a small JSON bridge over HTTP.
"""
