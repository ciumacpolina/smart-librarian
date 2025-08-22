from flask import Blueprint, request, jsonify, Response
from pathlib import Path
import os, tempfile, base64, uuid

from config import client  

media_bp = Blueprint("media", __name__)

# ---- error payload ----
def error_json(message, *, code="bad_request", status=400, hint=None):
    payload = {"error": {"code": code, "message": message}}
    if hint:
        payload["error"]["hint"] = hint
    return jsonify(payload), status


# ===================== TTS =====================
@media_bp.post("/tts")
def tts():
    """Text-to-speech (gpt-4o-mini-tts) -> MP3 bytes."""
    try:
        data = request.get_json(force=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return Response(status=204)

        # streaming path
        try:
            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice="alloy",
                input=text,
            ) as resp:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    tmp_path = tmp.name
                try:
                    resp.stream_to_file(tmp_path)
                    with open(tmp_path, "rb") as f:
                        mp3 = f.read()
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

            r = Response(mp3, mimetype="audio/mpeg")
            r.headers["Cache-Control"] = "no-store"
            return r

        except Exception:
            # fallback (non-streaming)
            try:
                audio = client.audio.speech.create(
                    model="gpt-4o-mini-tts",
                    voice="alloy",
                    input=text,
                )
                mp3 = getattr(audio, "content", None)
                if mp3 is None and hasattr(audio, "read"):
                    mp3 = audio.read()
                if not mp3:
                    return error_json("TTS returned empty audio.", code="upstream_error", status=502)

                r = Response(mp3, mimetype="audio/mpeg")
                r.headers["Cache-Control"] = "no-store"
                return r
            except Exception as e:
                print("TTS fallback error:", repr(e))
                return error_json("TTS service failed.", code="upstream_error", status=502)

    except Exception as e:
        print("TTS error:", repr(e))
        return error_json("Malformed request for TTS.", code="bad_request", status=400)


# ===================== STT =====================
# limits and accepted types
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB
ALLOWED_AUDIO_MIME = {
    "audio/webm", 
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
}

def _suffix_for_mime(m: str) -> str:
    m = (m or "").lower()
    if m == "audio/webm":
        return ".webm"
    if m == "audio/ogg":
        return ".ogg"
    if m == "audio/mpeg":
        return ".mp3"
    if m == "audio/mp4":
        return ".m4a"
    if m == "audio/wav":
        return ".wav"
    return ".bin"

@media_bp.post("/stt")
def stt():
    """
    Speech-to-Text:
      - receives multipart/form-data with 'audio' (webm)
      - transcribes with gpt-4o-transcribe (fallback whisper-1)
      - returns {"text": "..."} or {"text": ""} when silent/too small
    """
    try:
        f = request.files.get("audio")
        if not f:
            return jsonify({"text": ""}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            temp_path = tmp.name
            f.save(temp_path)

        try:
            # === guard against silence/very short audio ===
            try:
                if os.path.getsize(temp_path) < 5000:  
                    return jsonify({"text": ""})
            except Exception:
                pass

            with open(temp_path, "rb") as audio_file:
                try:
                    resp = client.audio.transcriptions.create(
                        model="gpt-4o-transcribe",
                        file=audio_file
                    )
                except Exception:
                    audio_file.seek(0)
                    resp = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )

            text = getattr(resp, "text", "") or ""
            return jsonify({"text": text})

        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    except Exception as e:
        print("STT error:", repr(e))
        return jsonify({"text": ""}), 500


# ===================== Image generation =====================
try:
    from config import GENERATED_IMAGES_DIR as _GEN_DIR
    GEN_DIR = Path(_GEN_DIR)
except Exception:
    GEN_DIR = Path("static") / "gen"
GEN_DIR.mkdir(parents=True, exist_ok=True)

@media_bp.post("/image")
def generate_image():
    """Image generation (gpt-image-1) -> {'url': '/static/gen/<file>.png'}."""
    try:
        data = request.get_json(force=True) or {}
        prompt  = (data.get("prompt")  or "").strip()
        size    = (data.get("size")    or "1024x1024").strip()
        quality = (data.get("quality") or "low").strip()

        if not prompt:
            return error_json("Empty prompt.", code="bad_request", status=400)

        if size not in {"1024x1024", "1024x1536", "1536x1024", "auto"}:
            size = "1024x1024"
        if quality not in {"low", "medium", "high", "auto"}:
            quality = "low"

        try:
            resp = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size=size,
                quality=quality,
            )
        except Exception as e:
            print("OpenAI image error:", repr(e))
            return error_json("Image API failed.", code="upstream_error", status=502)

        if not getattr(resp, "data", None):
            return error_json("Empty image response.", code="upstream_error", status=502)

        b64 = getattr(resp.data[0], "b64_json", None)
        if not b64:
            return error_json("No image payload.", code="upstream_error", status=502)

        try:
            img_bytes = base64.b64decode(b64)
        except Exception:
            return error_json("Invalid image payload.", code="upstream_error", status=502)

        fname = f"{uuid.uuid4().hex}.png"
        (GEN_DIR / fname).write_bytes(img_bytes)

        return jsonify({"url": f"/static/gen/{fname}"})

    except Exception as e:
        print("IMAGE error:", repr(e))
        return error_json("Image generation failed.", code="server_error", status=500)
