# Comandos de Arranque

## Orden de Inicio

1. **llamacpp-server** (siempre primero, `:8001`)
2. **Web Client** (`:8080`)
3. **Pipeline** (`:8765`)

---

## 1. llamacpp-server

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

**Verificar:**
```bash
curl http://localhost:8001/v1/models
# Debe devolver: "gemma-4-12b"
```

---

## 2. Web Client (HTTP Static)

```bash
setsid python3 -m http.server 8080 --directory /home/n/dev/speech-to-speech/client > /tmp/client.log 2>&1 &
```

**Logs:**
```bash
tail -f /tmp/client.log
```

**Hard refresh si cache:** `Ctrl+Shift+R` o `Ctrl+F5`

---

## 3. Pipeline (Realtime WebSocket)

```bash
setsid bash -c 'export OPENAI_API_KEY="not-needed" && /home/n/dev/speech-to-speech/.venv/bin/speech-to-speech --mode realtime --llm_backend responses-api --responses_api_base_url "http://localhost:8001/v1" --model_name "gemma-4-12b" --tts qwen3 --qwen3_tts_model_name "Qwen/Qwen3-TTS-12Hz-1.7B-Base" --responses_api_stream' > /tmp/pipeline.log 2>&1 &
```

**Logs:**
```bash
tail -f /tmp/pipeline.log
```

---

## Verificar Todo

```bash
# Servicios activos
ps aux | grep -E "llama-server|http.server|speech-to-speech" | grep -v grep

# Puertos escuchando
lsof -i :8001 | grep LISTEN  # llama.cpp
lsof -i :8080 | grep LISTEN  # web client
lsof -i :8765 | grep LISTEN  # pipeline
```

## Reiniciar Servicios

```bash
# Pipeline
pkill -f "speech-to-speech" 2>/dev/null; sleep 2
setsid bash -c '...' # (comando de pipeline de arriba)

# Web Client
lsof -ti :8080 | xargs kill 2>/dev/null; sleep 1
setsid python3 -m http.server 8080 --directory /home/n/dev/speech-to-speech/client > /tmp/client.log 2>&1 &
```

> **Importante:** Usar `setsid` para que los procesos sobrevivan cuando cambia la iteración de opencode. No usar `nohup`.
