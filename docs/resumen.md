# Speech-to-Speech - Voice Agent Local

Framework Hugging Face para construir **voice agents locales** con modelos de código abierto.

## Pipeline

Pipeline cascada: **VAD → STT → LLM → TTS** comunicando threads vía `queue.Queue`.

### Componentes Activos

| Etapa | Modelo | Backend | VRAM |
|-------|--------|---------|------|
| **VAD** | Silero VAD v5 | CPU | — |
| **STT** | Parakeet TDT 0.6B v3 | CUDA | ~2 GB |
| **LLM** | gemma-4-12b (Q4_K_XL) | llama.cpp (`:8001`) | ~7 GB |
| **TTS** | Qwen3-TTS-12Hz-1.7B-Base | faster-qwen3-tts (CUDA) | ~4 GB |

**VRAM total:** ~13 GB (GB10: 128 GB unificados)

## Hardware & Entorno

- **Hardware:** NVIDIA DGX Spark (GB10, 128 GB LPDDR5x unificados, 273 GB/s)
- **GPU:** Blackwell Architecture, 6,144 CUDA cores
- **CPU:** 20-core Arm (10 X925 + 10 A725)
- **OS:** Linux + CUDA

## Configación Actual

### Pipeline (modo `realtime`)

```bash
setsid bash -c 'export OPENAI_API_KEY="not-needed" && /home/n/dev/speech-to-speech/.venv/bin/speech-to-speech --mode realtime --llm_backend responses-api --responses_api_base_url "http://localhost:8001/v1" --model_name "gemma-4-12b" --tts qwen3 --qwen3_tts_model_name "Qwen/Qwen3-TTS-12Hz-1.7B-Base" --responses_api_stream' > /tmp/pipeline.log 2>&1 &
```

### llamacpp-server

```bash
llama-server \
  --model /mnt/ws1000/models/gemma-4-12b-it-UD-Q4_K_XL.gguf \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 64 \
  --alias gemma-4-12b \
  --port 8001 \
  --ctx-size 64000
```

| Argumento | Valor | Default | Nota |
|-----------|-------|---------|------|
| `--temp` | 1.0 | 0.80 | Más creativo |
| `--top-k` | 64 | 40 | Más opciones de tokens |
| `--top-p` | 0.95 | 0.95 | Iguales |
| `--ctx-size` | 64,000 | Model | Contexto extenso |
| `--n-gpu-layers` | auto | auto | GPU offload automático |
| `parallel` | 4 slots | auto | Soporta 4 conversaciones concurrentes |

### Web Client (HTTP + WebSocket)

```bash
setsid python3 -m http.server 8080 --directory /home/n/dev/speech-to-speech/client > /tmp/client.log 2>&1 &
```

- **HTTP:** `:8080` — Sirve `client/index.html`
- **WebSocket:** Nginx proxy `:443 → :8765`
- **Móvil:** Chrome soporta `getUserMedia` sobre HTTPS (cert autofirmado funciona)

### Voice Clone

- **Cache:** `TTS/voices/*.safetensors` (hash MD5 del `ref_audio`)
- **Generación:** Se crea al primer uso con `ref_audio`, se guarda y recarga al inicio
- **Modelo:** Solo `-Base` soporta voice cloning. `-CustomVoice` no acepta `ref_audio`

## Optimizaciones Activas

### 1. CPU Offload (`resample` + `base64`)
`audio.py:encode_audio_chunk()` usa `asyncio.to_thread()` → el event loop de asyncio no se bloquea durante resample+encoding.

### 2. TTS Streaming Chunk: 64 tokens
`qwen3_tts_handler.py:DEFAULT_FASTER_STREAMING_CHUNK_SIZE` = 64 (~5s por chunk). Reduce overhead de kernel launches; RTF más estable.

### 3. WebSocket Audio Batch: 16000 bytes
`websocket_router.py:MAX_AUDIO_BATCH_BYTES` = 16000 (~0.5s por envío). Con RTF >1 la cola se llena sola; menos mensajes WebSocket.

### 4. Inter-Turn Pause: 200ms
`qwen3_tts_handler.py` inyecta 200ms de silencio antes de cada nueva generación de TTS. Pausas naturales entre párrafos del LLM.

### 5. Echo Prevention (Cliente Web)
- `echoCancellation: false` → Señal raw sin distorsión del AEC del navegador
- **Mic mute:** `isPlaying` bloquea el micrófono durante TTS playback
- **Grace period:** 300ms post-playback para vaciar DAC del altavoz
- **Cancel button:** Envía `response.cancel` al server y limpia colas

### 6. VAD: `min_silence_ms = 600`
`VAD/vad_handler.py` → Tolerancia de 600ms de silencio antes de cerrar turno del usuario. Acepta dudas/pensamientos naturales dentro de una frase.

## Archivos Clave

| Archivo | Propósito |
|---------|-----------|
| `api/openai_realtime/handlers/audio.py` | `encode_audio_chunk` async + thread pool |
| `api/openai_realtime/websocket_router.py` | Send loop, batching, `MAX_AUDIO_BATCH_BYTES` |
| `TTS/qwen3_tts_handler.py` | Voice cache, inter-turn pause, streaming chunks, temperature |
| `VAD/vad_handler.py` | Silero VAD, `min_silence_ms`, speech detection |
| `client/index.html` | Web UI, echo prevention, cancel button |

## Comandos de Arranque

```bash
# 1) llamacpp-server (siempre primero)
llama-server ...

# 2) Web Client (port 8080)
setsid python3 -m http.server 8080 --directory /home/n/dev/speech-to-speech/client > /tmp/client.log 2>&1 &

# 3) Pipeline (realtime, port 8765)
setsid bash -c 'export OPENAI_API_KEY="not-needed" && /home/n/dev/speech-to-speech/.venv/bin/speech-to-speech ...' > /tmp/pipeline.log 2>&1 &
```

> **Importante:** Usar `setsid`, no `nohup`. Los procesos con `nohup` se killan cuando opencode cambia de iteración.

## Estado

- ✅ Voice clone cache loads on startup
- ✅ Echo prevention functional (PC + móvil)
- ✅ Cancel button works (stops TTS + clears server queues)
- ✅ RTF ~1.2–1.8 (under load)
- ✅ Concurrent slots: 4 (llama-server), 1 (pipeline)

## Roadmap (Brainstorm / En revisión)

- **Speaker Registry:** fingerprinting para identificar usuarios y asistentes
- **Multi-user:** calibración automática de nuevas voces
- **Multi-assistant:** switch de assistant + voz en runtime
- **ESP32:** hardware client con I2S mic/speaker
- **Multiuser docs:** ver `docs/multiuser.md`
