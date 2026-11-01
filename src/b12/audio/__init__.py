"""Локальний голосовий шар B-12: PTT, VAD/endpoint, ASR, TTS, AEC, speaker та full-duplex."""

from b12.audio.aec import AcousticEchoCanceller
from b12.audio.asr import TranscriptResult, WhisperAsr
from b12.audio.capture import MicController, PttCapture, inventory_devices
from b12.audio.duplex import BargeInResult, DuplexSession
from b12.audio.endpoint import EndpointDecision, EndpointDetector, SileroVad
from b12.audio.pipeline import VoicePipeline, VoiceTurnMetrics, VoiceTurnResult
from b12.audio.speaker import SpeakerMatch, SpeakerStore, SpeakerVerifier
from b12.audio.tts import AudioPlayer, PiperTts, SynthesizedAudio, split_sentences

__all__ = [
    "AcousticEchoCanceller",
    "AudioPlayer",
    "BargeInResult",
    "DuplexSession",
    "EndpointDecision",
    "EndpointDetector",
    "MicController",
    "PiperTts",
    "PttCapture",
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
    "inventory_devices",
    "split_sentences",
]
