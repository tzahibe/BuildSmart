"""Remote owner control plane (Telegram) on top of the orchestrator's state machine.

    transport.py    Telegram Bot API (long polling) + fake transport for tests
    commands.py     the typed owner command vocabulary, callback-button encoding, quick parser
    interpreter.py  natural language -> typed command (Opus via `claude -p`, read-only) + fake
    gateway.py      authorization, replay protection, audit, and the execution of typed commands
    voice.py        transcription adapter (voice enters the same command path; never authorizes a merge)
    service.py      the deterministic polling process (`agentctl remote start`)

The LLM only interprets intent. Every mutation is a typed command the gateway validates against
the authoritative state (GitHub + orchestrator DB) immediately before executing it.
"""
