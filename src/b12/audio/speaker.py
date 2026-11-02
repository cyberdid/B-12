"""Верифікація мовця (speaker identity), анти-спуфінг/replay та життєвий цикл біометричних даних.

Інваріанти безпеки (Spec §12, Task 17):
- Схожість голосу НІКОЛИ не надає авторизації чи прав інструментів (це лише метадані спостереження).
- Реєстрація (enrollment) дозволена виключно через автентифікований контрольний шлях власника,
  ніколи через текстовий вивід або tool call моделі.
- Видалення актора або профілю фізично затирає біометричний вектор (`secure_delete = ON`).
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


def extract_voiceprint(
    audio_16k: np.ndarray, sample_rate: int = 16000
) -> tuple[np.ndarray, str, bool]:
    """Обчислити нормований спектрально-гармонічний вектор голосу, SHA-256 та ознаку спуфінгу."""
    samples = np.asarray(audio_16k, dtype=np.float32).reshape(-1)
    pcm16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16).tobytes()
    audio_hash = hashlib.sha256(pcm16).hexdigest()

    if len(samples) < 1600:
        raise ValueError("audio_too_short_for_voiceprint")

    # Frame-based short-time Fourier spectrum (512-sample frames, 256 hop)
    win = np.hanning(512).astype(np.float32)
    frames = []
    for i in range(0, len(samples) - 512 + 1, 256):
        segment = samples[i : i + 512]
        if float(np.sqrt(np.mean(segment * segment))) > 0.01:
            spec = np.abs(np.fft.rfft(segment * win))
            frames.append(spec)

    if not frames:
        raise ValueError("no_voiced_frames_for_voiceprint")

    mag = np.stack(frames, axis=0)  # (T, 257)
    mean_spec = np.mean(mag, axis=0)
    std_spec = np.std(mag, axis=0)

    # Anti-spoof check: extreme spectral flatness (white noise) or clipped DC
    geo_mean = float(np.exp(np.mean(np.log(mean_spec + 1e-8))))
    arith_mean = float(np.mean(mean_spec) + 1e-8)
    flatness = geo_mean / arith_mean
    is_spoof = flatness > 0.85

    # Log-mel-like 32 frequency bands + 16 cepstral (DCT-II) coefficients + pitch harmonic profile
    freqs = np.linspace(0, sample_rate / 2.0, len(mean_spec))
    mel_edges = np.geomspace(60.0, 7600.0, 34)
    band_means = np.zeros(32, dtype=np.float32)
    band_stds = np.zeros(32, dtype=np.float32)
    for b in range(32):
        mask = (freqs >= mel_edges[b]) & (freqs < mel_edges[b + 2])
        if np.any(mask):
            band_means[b] = float(np.log1p(np.mean(mean_spec[mask])))
            band_stds[b] = float(np.log1p(np.mean(std_spec[mask])))

    # DCT-II cepstral liftering (16 MFCC-like coefficients invariant to gain)
    n_bands = 32
    k_idx = np.arange(1, 17)[:, None]
    n_idx = np.arange(n_bands)[None, :]
    dct_basis = np.cos(np.pi * k_idx * (2 * n_idx + 1) / (2.0 * n_bands)).astype(np.float32)
    cepstral = dct_basis @ (band_means - np.mean(band_means))
    cepstral = cepstral / (np.linalg.norm(cepstral) + 1e-8)

    band_feats = np.empty(64, dtype=np.float32)
    band_feats[0::2] = band_means
    band_feats[1::2] = band_stds
    band_feats = band_feats / (np.linalg.norm(band_feats) + 1e-8)

    # Fine-grained harmonic peak bins in fundamental frequency region (70 Hz .. 450 Hz)
    f0_mask = (freqs >= 70.0) & (freqs <= 450.0)
    f0_profile = mean_spec[f0_mask]
    f0_profile = f0_profile / (np.linalg.norm(f0_profile) + 1e-8)

    vec = np.concatenate(
        [
            band_feats * 1.5,
            cepstral * 2.0,
            f0_profile.astype(np.float32) * 2.5,
        ]
    )
    norm = float(np.linalg.norm(vec))
    if norm > 1e-8:
        vec = vec / norm
    return vec, audio_hash, is_spoof


@dataclass(frozen=True)
class SpeakerMatch:
    matched: bool
    actor_id: str | None
    score: float
    threshold: float
    is_spoof_or_replay: bool


class SpeakerStore:
    """SQLite-сховище голосових профілів з фізичним затиранням при видаленні."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA secure_delete = ON")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS speaker_profiles (
                actor_id TEXT PRIMARY KEY,
                embedding_json TEXT NOT NULL,
                enrolled_hashes_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    def save_profile(self, actor_id: str, embedding: np.ndarray, audio_hash: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        row = self._conn.execute(
            "SELECT enrolled_hashes_json FROM speaker_profiles WHERE actor_id = ?",
            (actor_id,),
        ).fetchone()
        hashes = json.loads(row["enrolled_hashes_json"]) if row else []
        if audio_hash not in hashes:
            hashes.append(audio_hash)
        self._conn.execute(
            """
            INSERT INTO speaker_profiles(actor_id, embedding_json, enrolled_hashes_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(actor_id) DO UPDATE SET
                embedding_json = excluded.embedding_json,
                enrolled_hashes_json = excluded.enrolled_hashes_json,
                created_at = excluded.created_at
            """,
            (actor_id, json.dumps(embedding.tolist()), json.dumps(hashes), now),
        )
        return {"actor_id": actor_id, "created_at": now, "samples": len(hashes)}

    def list_profiles(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT actor_id, embedding_json, enrolled_hashes_json, created_at "
            "FROM speaker_profiles"
        ).fetchall()
        return [
            {
                "actor_id": r["actor_id"],
                "embedding": np.asarray(json.loads(r["embedding_json"]), dtype=np.float32),
                "hashes": set(json.loads(r["enrolled_hashes_json"])),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def delete_actor(self, actor_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM speaker_profiles WHERE actor_id = ?", (actor_id,))
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return cur.rowcount > 0

    def purge_evidence(self, actor_id: str, target_ids: tuple[str, ...] = ()) -> bool:
        """Видалити голосовий профіль актора при повному забутті або за явною ціллю."""
        if not target_ids or actor_id in target_ids or f"voice:{actor_id}" in target_ids:
            return self.delete_actor(actor_id)
        return False

    def close(self) -> None:
        self._conn.close()


class SpeakerVerifier:
    """Контрольована реєстрація та верифікація голосу із захистом від exact-replay атак."""

    def __init__(self, store: SpeakerStore, control, *, threshold: float = 0.88):
        self.store = store
        self.control = control
        self.threshold = threshold

    def enroll(
        self,
        *,
        actor_id: str,
        caller_actor_id: str,
        audio_16k: np.ndarray,
    ) -> dict[str, Any]:
        """Зареєструвати голосовий еталон; дозволено лише власнику або актору зі згодою."""
        caller = self.control.resolve_actor(caller_actor_id)
        target = self.control.resolve_actor(actor_id)
        if not caller.owner and (caller.id != target.id or not target.consent):
            raise PermissionError("speaker_enrollment_requires_owner_or_consented_actor")
        if not target.consent and not target.owner:
            raise PermissionError("consent_required_for_biometric_enrollment")

        vec, audio_hash, is_spoof = extract_voiceprint(audio_16k)
        if is_spoof:
            raise ValueError("spoof_audio_rejected")
        return self.store.save_profile(target.id, vec, audio_hash)

    def verify(self, audio_16k: np.ndarray) -> SpeakerMatch:
        """Перевірити, чи належить голос зареєстрованому актору; відхилити replay або spoof."""
        try:
            vec, audio_hash, is_spoof = extract_voiceprint(audio_16k)
        except ValueError:
            return SpeakerMatch(False, None, 0.0, self.threshold, False)

        profiles = self.store.list_profiles()
        if not profiles:
            return SpeakerMatch(False, None, 0.0, self.threshold, is_spoof)

        for prof in profiles:
            if audio_hash in prof["hashes"]:
                # Exact bit-for-bit replay of an enrollment recording is blocked!
                return SpeakerMatch(False, None, 0.0, self.threshold, True)

        if is_spoof:
            return SpeakerMatch(False, None, 0.0, self.threshold, True)

        best_actor: str | None = None
        best_score = -1.0
        for prof in profiles:
            emb = prof["embedding"]
            if len(emb) != len(vec):
                continue
            score = float(np.dot(vec, emb) / (np.linalg.norm(vec) * np.linalg.norm(emb) + 1e-8))
            if score > best_score:
                best_score = score
                best_actor = prof["actor_id"]

        matched = best_score >= self.threshold and best_actor is not None
        return SpeakerMatch(
            matched=matched,
            actor_id=best_actor if matched else None,
            score=round(max(0.0, best_score), 4),
            threshold=self.threshold,
            is_spoof_or_replay=False,
        )
