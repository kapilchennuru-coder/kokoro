# Generates a Kokoro voice file for one patient on demand from the
# web app, instead of the old batch script that ran over a whole
# Excel file at once. Keeps a single loaded KPipeline (loading it is
# slow) reused across calls in this process.

import os

import numpy as np
import soundfile as sf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "..", "audio")  # same folder Asterisk's audio/ maps to

LANG_CODE = "a"
VOICE_NAME = "af_jessica"
SAMPLE_RATE = 24000

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code=LANG_CODE)
    return _pipeline


def build_call_script(patient_name: str, balance_amount: float) -> str:
    return (
        f"Hello, this is Zebl AR agent calling. This call is regarding your "
        f"account for {patient_name}. Your current "
        f"outstanding balance is ${balance_amount:.2f}. Thank you for taking the call."
    )


def generate_patient_audio(patient_id: str, patient_name: str, balance_amount: float) -> str:
    """Returns the audio filename (no extension) written into AUDIO_DIR."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    pipeline = _get_pipeline()
    script = build_call_script(patient_name, balance_amount)

    generator = pipeline(script, voice=VOICE_NAME)
    audio_chunks = [audio for _, _, audio in generator]
    audio = audio_chunks[0] if len(audio_chunks) == 1 else np.concatenate(audio_chunks)

    filename_no_ext = f"patient_{patient_id}_voice"
    output_path = os.path.join(AUDIO_DIR, f"{filename_no_ext}.wav")
    sf.write(output_path, audio, SAMPLE_RATE)
    return filename_no_ext
