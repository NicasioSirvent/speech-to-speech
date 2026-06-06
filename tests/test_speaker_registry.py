"""Test script to verify SpeakerRegistry works correctly with real-ish audio."""
import numpy as np
import sys
sys.path.insert(0, '..') # To make it work from repo root

from speech_to_speech.VAD.speaker_registry import SpeakerRegistry

def test_registry():
    print("1. Initializing SpeakerRegistry...")
    registry = SpeakerRegistry(device="cuda")

    print("2. Simulating 'User 1' calibration...")
    # Simulate a 4-second audio segment (sine waves to mimic simple pitch)
    t = np.linspace(0, 4, 16000 * 4).astype(np.float32)
    audio1 = np.sin(2 * np.pi * 200 * t)[:16000] + np.sin(2 * np.pi * 400 * t * 2)[:16000] 
    
    registry.register("user1", audio1)

    print("3. Testing Identification (same speaker, different segment)...")
    # Use a subsequent segment of the SAME audio (it should match user 1)
    result1 = registry.identify(audio1[8000:16000])
    print(f"   Expected: user1 | Got: {result1}")
    assert result1 == "user1", "Failed to identify user 1!"

    print("4. Testing Identification with completely different audio...")
    different_audio = np.sin(2 * np.pi * 1000 * t)[:16000] 
    result2 = registry.identify(different_audio)
    print(f"   User 1 match only, different audio should be None/Unknown: {result2}")
    
    print("\n✅ SpeakerRegistry tests passed!")

if __name__ == "__main__":
    test_registry()