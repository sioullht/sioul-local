"""
s(i)oul – Sprachfunktionen, komplett lokal
- Whisper (faster-whisper): Sprache -> Text
- Piper: Text -> Sprache, mit deutscher und englischer Stimme
Die Modelle werden beim ersten Start einmal heruntergeladen und im Ordner
models/ gespeichert. Danach funktioniert alles ohne Internet.
"""
import io
import os
import re
import ssl
import tempfile
import threading
import urllib.request
import wave

import certifi

DATA = os.environ.get("VOICE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))
WHISPER_SIZE = os.environ.get("WHISPER_MODEL", "small")
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
VOICES = {
    "de": os.environ.get("PIPER_VOICE_DE", "de/de_DE/thorsten/medium/de_DE-thorsten-medium"),
    "en": os.environ.get("PIPER_VOICE_EN", "en/en_US/lessac/medium/en_US-lessac-medium"),
}

state = {"status": "off", "error": None}
_whisper = None
_voices = {}
_start_lock = threading.Lock()
_stt_lock = threading.Lock()
_tts_lock = threading.Lock()


def _download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return
    print("  lade", os.path.basename(dest), "...", flush=True)
    tmp = dest + ".part"
    # Zertifikate von certifi, weil Python auf macOS sonst keine findet
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, timeout=60, context=ctx) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)


def _prepare():
    global _whisper
    try:
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
        from piper import PiperVoice

        os.makedirs(DATA, exist_ok=True)

        wdir = os.path.join(DATA, "whisper-" + WHISPER_SIZE)
        if not os.path.exists(os.path.join(wdir, "model.bin")):
            print(f"Whisper ({WHISPER_SIZE}) wird einmalig heruntergeladen ...", flush=True)
            download_model(WHISPER_SIZE, output_dir=wdir)
        _whisper = WhisperModel(wdir, device="cpu", compute_type="int8")

        pdir = os.path.join(DATA, "piper")
        os.makedirs(pdir, exist_ok=True)
        for lang, path in VOICES.items():
            onnx = os.path.join(pdir, path.rsplit("/", 1)[-1] + ".onnx")
            _download(PIPER_BASE + path + ".onnx", onnx)
            _download(PIPER_BASE + path + ".onnx.json", onnx + ".json")
            _voices[lang] = PiperVoice.load(onnx)

        state.update(status="ready", error=None)
        print("Sprachfunktionen bereit (Whisper + Piper).", flush=True)
    except Exception as e:
        msg = str(e)
        if "403" in msg or "404" in msg or "urlopen" in msg or "Connection" in msg or "resolve" in msg.lower():
            msg = "Download der Sprachmodelle fehlgeschlagen. Beim ersten Start wird einmal Internet gebraucht. (" + msg + ")"
        state.update(status="error", error=msg)
        print("Sprachfunktionen nicht verfügbar:", msg, flush=True)


def start():
    """Modelle im Hintergrund laden (bzw. beim ersten Mal herunterladen)."""
    with _start_lock:
        if state["status"] in ("loading", "ready"):
            return
        state.update(status="loading", error=None)
    threading.Thread(target=_prepare, daemon=True).start()


# ---------- Sprache -> Text ----------
def _decode(path, rate=16000):
    """Aufnahme (webm/mp4/ogg/wav) in 16-kHz-Mono für Whisper umwandeln.
    Eigene Umsetzung, weil faster-whisper mit neuen PyAV-Versionen nicht mehr kompatibel ist."""
    import av
    import numpy as np

    chunks = []
    with av.open(path, mode="r") as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        for frame in container.decode(stream):
            for f in resampler.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def transcribe(data, suffix=".webm"):
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        audio = _decode(path)
        if audio.size < 1600:  # unter 0,1 Sekunden
            return {"text": "", "language": None}
        with _stt_lock:
            segments, info = _whisper.transcribe(audio, beam_size=1, vad_filter=True)
            # Nur Deutsch oder Englisch zulassen (kurze Aufnahmen werden sonst manchmal falsch erkannt)
            if info.language not in ("de", "en"):
                probs = dict(getattr(info, "all_language_probs", None) or [])
                lang = "en" if probs.get("en", 0) > probs.get("de", 0) else "de"
                segments, info = _whisper.transcribe(audio, beam_size=1, vad_filter=True, language=lang)
            text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "language": info.language}
    finally:
        os.unlink(path)


# ---------- Text -> Sprache ----------
_DE = ("der", "die", "das", "und", "ist", "nicht", "ich", "du", "ein", "eine", "zu", "mit",
       "auch", "sie", "es", "wie", "für", "auf", "dass", "sind", "wir", "kann", "oder")
_EN = ("the", "and", "is", "are", "you", "not", "with", "this", "that", "for", "to", "of",
       "it", "i", "can", "your", "what", "be", "have", "on")


def detect_lang(text):
    words = re.findall(r"[a-zäöüß']+", text.lower())
    de = sum(w in _DE for w in words) + 2 * len(re.findall(r"[äöüß]", text.lower()))
    en = sum(w in _EN for w in words)
    return "en" if en > de else "de"


def speak(text, lang=None):
    text = re.sub(r"[\U00010000-\U0010FFFF]", "", text)  # Emojis nicht vorlesen
    text = re.sub(r"\s+\n", "\n", text).strip()[:6000]
    if lang not in _voices:
        lang = detect_lang(text)
    voice = _voices.get(lang) or next(iter(_voices.values()))
    buf = io.BytesIO()
    with _tts_lock, wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf)
    return buf.getvalue(), lang