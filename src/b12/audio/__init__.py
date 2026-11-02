"""Локальна голосова підсистема B-12: PTT, VAD/endpoint, ASR, TTS, AEC, Duplex, Speaker."""

from b12.audio.aec import AcousticEchoCanceller, AecStats, PulseAudioWebRtcAec
from b12.audio.asr import TranscriptResult, WhisperAsr
from b12.audio.capture import MicController, PttCapture, inventory_devices
from b12.audio.duplex import BargeInResult, DuplexSession
from b12.audio.endpoint import EndpointDecision, EndpointDetector, SileroVad
from b12.audio.pipeline import VoicePipeline, VoiceTurnMetrics, VoiceTurnResult
from b12.audio.speaker import SpeakerMatch, SpeakerStore, SpeakerVerifier
from b12.audio.tts import AudioPlayer, PiperTts, SynthesizedAudio, extract_stream_clauses

__all__ = [
    "AcousticEchoCanceller",
    "AecStats",
    "AudioPlayer",
    "BargeInResult",
    "DuplexSession",
    "EndpointDecision",
    "EndpointDetector",
    "MicController",
    "PiperTts",
    "PttCapture",
    "PulseAudioWebRtcAec",
    "SileroVad",
    "SpeakerMatch",
    "SpeakerStore",
    "SpeakerVerifier",
    "SynthesizedAudio",
    "TranscriptResult",
    "VoicePipeline",
    "VoiceTurnMetrics",
    "VoiceTurnResult",
    "WhisperAsr",
    "extract_stream_clauses",
    "inventory_devices",
]
