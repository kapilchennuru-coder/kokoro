# Kokoro TTS adapter for the calling dashboard.
# Keeps a single loaded KPipeline (loading is slow) reused across calls.
# Frontend/API must not import kokoro directly — go through this module.

import os

import numpy as np
import soundfile as sf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "..", "audio")  # same folder Asterisk's audio/ maps to

LANG_CODE = "a"
VOICE_NAME = "af_jessica"
SAMPLE_RATE = 24000

DEFAULT_OPENING = (
    "Hello {name}, this is a courtesy call from {hospital}. "
    "Our records show you have a pending balance of {balance_display}. "
    "Please contact the billing office at your earliest convenience. Thank you."
)

_pipeline = None
_pipeline_error = None


def _get_pipeline():
    global _pipeline, _pipeline_error
    if _pipeline is not None:
        return _pipeline
    if _pipeline_error is not None:
        raise RuntimeError(_pipeline_error)
    try:
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code=LANG_CODE)
        return _pipeline
    except Exception as exc:
        _pipeline_error = "Unable to process voice requests right now."
        raise RuntimeError(_pipeline_error) from exc


def tts_available() -> dict:
    try:
        _get_pipeline()
        return {"available": True, "detail": "Ready"}
    except Exception:
        return {"available": False, "detail": "Unable to process voice requests right now."}


def build_call_script(patient_name: str, balance_amount: float) -> str:
    """Legacy helper preserved for patient reminder calls."""
    return (
        f"Hello, this is Zebl AR agent calling. This call is regarding your "
        f"account for {patient_name}. Your current "
        f"outstanding balance is ${balance_amount:.2f}. Thank you for taking the call."
    )


def generate_call_audio(
    contact_id: str,
    script: str,
    voice_name: str = VOICE_NAME,
    speed: float = 1.0,
) -> str:
    """Generate WAV via Kokoro. Returns filename without extension (for Asterisk)."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    pipeline = _get_pipeline()

    # British voices use lang_code 'b' — recreate pipeline if needed
    lang = "b" if voice_name.startswith("b") else "a"
    global _pipeline
    if getattr(pipeline, "lang_code", LANG_CODE) != lang:
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code=lang)
        pipeline = _pipeline

    generator = pipeline(script, voice=voice_name, speed=speed)
    audio_chunks = [audio for _, _, audio in generator]
    if not audio_chunks:
        raise RuntimeError("Unable to process this request right now.")
    audio = audio_chunks[0] if len(audio_chunks) == 1 else np.concatenate(audio_chunks)

    filename_no_ext = f"contact_{contact_id}_voice"
    output_path = os.path.join(AUDIO_DIR, f"{filename_no_ext}.wav")
    sf.write(output_path, audio, SAMPLE_RATE)
    return filename_no_ext


def generate_patient_audio(patient_id: str, patient_name: str, balance_amount: float) -> str:
    """Legacy wrapper — preserved for existing patient call path."""
    script = build_call_script(patient_name, balance_amount)
    return generate_call_audio(
        contact_id=f"patient_{patient_id}",
        script=script,
        voice_name=VOICE_NAME,
        speed=1.0,
    )
