import asyncio
import base64
import json
import logging
import os

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

load_dotenv()
app = FastAPI()

# Configure CORS (Adjust as needed for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("BASE_URL")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

logger.info(f"Stream URL being used: {BASE_URL}/media-stream")


@app.get("/test")
async def test():
    logger.info("Test endpoint hit")
    print("Test endpoint hit")
    return {
        "message": "Server is reachable",
        "routes": {
            "test": f"{BASE_URL}/test",
            "call_customer": f"{BASE_URL}/call-customer",
            "handle_call": f"{BASE_URL}/handle-call",
            "media_stream": f"{BASE_URL}/media-stream",
        },
        "base_url": BASE_URL,
        "timestamp": "Right now!",
    }


# Endpoint to initiate a call to customer
@app.post("/call-customer")
async def call_customer(request: Request):
    try:
        data = await request.json()
        customer_phone = data.get("customer_phone_number")

        if not customer_phone:
            raise HTTPException(
                status_code=400, detail="Customer phone number required"
            )

        # Format phone number
        if not customer_phone.startswith("+"):
            customer_phone = f"+{customer_phone}"

        # Build and verify webhook URL
        webhook_url = f"{BASE_URL}/handle-call"
        logger.info(f"Using webhook URL: {webhook_url}")

        # Verify URL format
        if not webhook_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL format: {webhook_url}")

        logger.info("Making call with parameters:")
        logger.info(f"To: {customer_phone}")
        logger.info(f"From: {TWILIO_PHONE_NUMBER}")
        logger.info(f"Webhook URL: {webhook_url}")

        # Create call
        call = twilio_client.calls.create(
            url=webhook_url, to=customer_phone, from_=TWILIO_PHONE_NUMBER
        )

        logger.info(f"Call initiated with SID: {call.sid}")
        return {"status": "success", "call_sid": call.sid}

    except Exception as e:
        logger.error(f"Error initiating call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# TwiML endpoint that handles the call setup
@app.post("/handle-call")
async def handle_call(request: Request):
    try:
        logger.info("Generating TwiML for call")
        response = VoiceResponse()

        # Play connecting message
        response.say("Connecting to AI assistant", voice="alice")
        response.pause(length=1)

        # Use wss:// for the Stream URL
        stream_url = f"wss://{BASE_URL.split('://')[1]}/media-stream"  # Extract domain from BASE_URL
        logger.info(f"Setting up stream URL: {stream_url}")

        # Start media stream
        connect = Connect()
        connect.stream(url=stream_url)
        response.append(connect)

        generated_twiml = str(response)
        logger.info(f"Generated TwiML: {generated_twiml}")
        return Response(content=generated_twiml, media_type="application/xml")
    except Exception as e:
        logger.error(f"Error in handle-call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint that handles the real-time audio stream
@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    logger.info("WebSocket endpoint hit")
    print("WebSocket endpoint hit")

    stream_sid = None
    openai_ws = None

    try:
        await websocket.accept()
        logger.info("WebSocket connection accepted")
        print("WebSocket connection accepted")

        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type = data.get("event", "unknown")
                logger.info(f"Received message type: {event_type}")
                print(f"Received message type: {event_type}")

                if event_type == "connected":
                    logger.info("WebSocket connected")
                    print("WebSocket connected")
                    continue  # Wait for 'start' event

                elif event_type == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"Stream started with SID: {stream_sid}")
                    print(f"Stream started with SID: {stream_sid}")

                    # Connect to OpenAI's Realtime API
                    try:
                        openai_ws = await websockets.connect(
                            "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
                            extra_headers={
                                "Authorization": f"Bearer {OPENAI_API_KEY}",
                                "OpenAI-Beta": "realtime=v1",
                            },
                        )
                        logger.info("Connected to OpenAI")
                        print("Connected to OpenAI")

                        # Initialize OpenAI session
                        session_update = {
                            "type": "session.update",
                            "session": {
                                "input_audio_format": "g711_ulaw",
                                "output_audio_format": "g711_ulaw",
                                "voice": "alloy",
                                "temperature": 0.7,
                            },
                        }
                        await openai_ws.send(json.dumps(session_update))
                        logger.info("Sent session update to OpenAI")
                        print("Sent session update to OpenAI")

                        # Send welcome message
                        welcome_message = {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Hello! I'm an AI assistant. How can I help you today?",
                                    }
                                ],
                            },
                        }
                        await openai_ws.send(json.dumps(welcome_message))
                        await openai_ws.send(json.dumps({"type": "response.create"}))
                        logger.info(
                            "Sent welcome message and response.create to OpenAI"
                        )
                        print("Sent welcome message and response.create to OpenAI")

                    except Exception as openai_error:
                        logger.error(f"OpenAI connection error: {str(openai_error)}")
                        print(f"OpenAI connection error: {str(openai_error)}")
                        continue  # Keep the WebSocket connection alive

                elif event_type == "media":
                    if openai_ws:
                        audio_payload = data["media"]["payload"]
                        # Optional: Convert audio if necessary
                        # audio_payload = convert_audio(audio_payload)
                        await openai_ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": audio_payload,
                                }
                            )
                        )
                        logger.info("Sent audio to OpenAI")
                        print("Sent audio to OpenAI")
                    else:
                        logger.warning("Received media before start event")
                        print("Received media before start event")

                elif event_type == "stop":
                    logger.info("Stream stopped by Twilio")
                    print("Stream stopped by Twilio")
                    if openai_ws:
                        await openai_ws.close()
                        logger.info("Closed OpenAI WebSocket connection")
                        print("Closed OpenAI WebSocket connection")
                    break  # Exit the loop to close the WebSocket

                else:
                    logger.warning(f"Unhandled event type: {event_type}")
                    print(f"Unhandled event type: {event_type}")

                # Handle OpenAI responses concurrently
                if openai_ws:
                    try:
                        openai_message = await openai_ws.recv()
                        openai_response = json.loads(openai_message)
                        logger.info(f"Received OpenAI message: {openai_response}")
                        print(f"Received OpenAI message: {openai_response}")

                        if openai_response.get("type") == "response.audio.delta":
                            await websocket.send_json(
                                {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {"payload": openai_response["delta"]},
                                }
                            )
                            logger.info("Sent audio delta to Twilio")
                            print("Sent audio delta to Twilio")

                        elif openai_response.get("type") == "error":
                            error = openai_response.get("error", {})
                            logger.error(f"OpenAI error: {error}")
                            print(f"OpenAI error: {error}")

                    except websockets.exceptions.ConnectionClosed as e:
                        logger.error(f"OpenAI WebSocket connection closed: {e}")
                        print(f"OpenAI WebSocket connection closed: {e}")
                        break  # Exit the loop to close the WebSocket
                    except Exception as e:
                        logger.error(f"Error receiving OpenAI messages: {e}")
                        print(f"Error receiving OpenAI messages: {e}")
                        break

            except json.JSONDecodeError:
                logger.error("Received invalid JSON message")
                print("Received invalid JSON message")
                continue  # Continue listening for valid messages
            except Exception as e:
                logger.error(f"Error handling message: {str(e)}")
                print(f"Error handling message: {str(e)}")
                break  # Exit the loop to close the WebSocket

    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
        print(f"WebSocket connection error: {str(e)}")

    finally:
        if openai_ws:
            await openai_ws.close()
            logger.info("Closed OpenAI WebSocket connection in finally block")
            print("Closed OpenAI WebSocket connection in finally block")
        logger.info("WebSocket connection closed")
        print("WebSocket connection closed")


if __name__ == "__main__":
    import uvicorn

    print("Starting server...")
    print(f"BASE_URL: {BASE_URL}")
    print("Available routes:")
    print(" - GET /test")
    print(" - POST /call-customer")
    print(" - POST /handle-call")
    print(" - WebSocket /media-stream")

    uvicorn.run(app, host="0.0.0.0", port=5050)
