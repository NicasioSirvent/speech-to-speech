"""Speaker Registry for multi-user/multi-assistant environment."""
from __future__ import annotations

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

class SpeakerRegistry:
    """Manages speaker fingerprints for the shared room environment.
    Uses eCAPA-Voice (SpeechBrain) for embedding generation.
    """

    def __init__(self, device: str = "cuda"):
        self._encoder = None
        self._device = device
        self._fingerprints = {}  # user_id -> embedding (normalized)
        self.threshold = 0.5  # Default similarity threshold

    def _ensure_encoder(self):
        if self._encoder is None:
            import torch
            from speechbrain.pretrained import EncoderClassifier

            logger.info("Loading eCAPA-Voice encoder (SpeechBrain)...")
            self._encoder = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="./tmpdir",
                run_opts={"device": self._device},
            )
            self._encoder.eval()
            logger.info("eCAPA-Voice encoder loaded.")

    def _get_embedding(self, audio: np.ndarray) -> np.ndarray:
        """Generates a normalized embedding for a given audio chunk.
        Args:
            audio: Numpy array of audio samples (mono, float32/int16, 16kHz)
        """
        self._ensure_encoder()
        import torch

        # Prepare audio
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.dtype == np.float32 and np.max(np.abs(audio)) > 1.0:
            audio = audio / 32768.0
            
        # Resample if needed (eCAPA expects 16kHz)
        # Assuming 16kHz for now, will add robust resampling later if needed.
        target_length = int(2.0 * 16000) # 2 seconds
        if len(audio) < target_length:
            audio = np.pad(audio, (0, target_length - len(audio)))
        else:
            audio = audio[:target_length]

        audio_tensor = torch.from_numpy(audio).unsqueeze(0)
        with torch.no_grad():
            embedding = self._encoder.encode_batch(audio_tensor)
            
        return self._normalize(embedding.cpu().numpy().flatten())

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))

    def register(self, user_id: str, audio_chunk: np.ndarray):
        """Registers a new speaker or updates their fingerprint.
        Updates using exponential moving average for robustness.
        """
        logger.info(f"Calibrating fingerprint for '{user_id}' ...")
        embedding = self._get_embedding(audio_chunk)
        
        if user_id in self._fingerprints:
            # Rolling update (simple EMA with alpha 0.3)
            current = self._fingerprints[user_id]
            self._fingerprints[user_id] = self._normalize(0.7 * current + 0.3 * embedding)
        else:
            self._fingerprints[user_id] = embedding
        
        logger.info(f"Fingerprint for '{user_id}' registered.")

    def identify(self, audio_chunk: np.ndarray) -> Optional[str]:
        """Identifies the speaker by comparing against registered fingerprints.
        Returns user_id if confidence > threshold, else None.
        """
        if not self._fingerprints:
            return None
            
        embedding = self._get_embedding(audio_chunk)
        best_score = -1.0
        best_user = None

        for user_id, fp in self._fingerprints.items():
            score = self._cosine_similarity(fp, embedding)
            if score > best_score:
                best_score = score
                best_user = user_id

        if best_user and best_score >= self.threshold:
            logger.info(f"Identified: '{best_user}' (similarity: {best_score:.3f})")
            return best_user
        return None

    def has(self, user_id: str) -> bool:
        return user_id in self._fingerprints

    def __repr__(self):
        return f"SpeakerRegistry(users={len(self._fingerprints)}, threshold={self.threshold})"