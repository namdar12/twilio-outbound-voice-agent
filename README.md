# Twilio Outbound Voice Agent (OpenAI Realtime API)

Place AI-powered outbound phone calls. A FastAPI server triggers a Twilio
call to any phone number, streams the call audio over a WebSocket, and bridges
it to OpenAI's Realtime API for a live two-way voice conversation.

## Architecture

```
POST /call-customer --Twilio REST--> outbound call --> callee answers
Twilio --TwiML <Connect><Stream>--> wss://<BASE_URL>/media-stream
/media-stream <--Twilio audio (G.711 μ-law)--> OpenAI Realtime API (WebSocket)
```

- `outboundMainv2.py` — the whole app: `/call-customer` initiates the call,
`/handle-call` returns TwiML that opens the media stream, `/media-stream`
relays audio between Twilio and OpenAI and plays the AI's voice back to the
caller.

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment:

   ```bash
   cp .env.example .env   # then fill in your keys
   ```

   You need a Twilio account with a voice-capable number and an OpenAI API key
with Realtime API access.

3. Run the server (default port 5050):

   ```bash
   python outboundMainv2.py
   ```

4. Expose it publicly (e.g. `ngrok http 5050`) and set `BASE_URL` to that URL.

5. Trigger a call:

   ```bash
   curl -X POST http://localhost:5050/call-customer \
     -H 'Content-Type: application/json' \
     -d '{"customer_phone_number": "+15551234567"}'
   ```

## Configuration

| Variable | Required | Description |
|---|---|---|
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | yes | Twilio credentials |
| `TWILIO_PHONE_NUMBER` | yes | Your Twilio voice number (caller ID) |
| `OPENAI_API_KEY` | yes | OpenAI key with Realtime API access |
| `BASE_URL` | yes | Public URL of this server, no trailing slash |

## Notes

- The OpenAI Realtime model string (`gpt-4o-realtime-preview-2024-10-01`) is
pinned from when this was built — update it to a current model if needed.
- `speech-assistant-openai-realtime-api-python/` is a local copy of Twilio's
official sample repo kept for reference; it's excluded from version control.
- Never commit `.env` — it's gitignored.
