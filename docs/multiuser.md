# Multi-User & Multi-Assistant Architecture

## Estado
🧠 Brainstorm / Roadmap. No implementado aún. Ver `docs/resumen.md` para funcionalidad actual.

## Goal
Soportar múltiples usuarios y múltiples asistentes en una sesión compartida, con reconocimiento de voz y enrutamiento dinámico.

## Core Concept: "Shared Room" (Sala Compartida)
- **Un solo KV Cache:** toda la conversación se mantiene en un solo hilo. No hay aislamiento de sesiones.
- **Speaker Registry:** fingerprinting en tiempo real para identificar qué participante habla.
- **Dynamic Routing:** el LLM decide qué asistente responde según el contexto/intención del usuario.
- **Dramaturgo Mode:** los asistentes pueden hablar entre ellos en secuencia, controlados por el LLM.

## 1. Speaker Registry (`SpeakerRegistry`)
Base de datos de fingerprints de todos los participantes.

| Speaker | Fuente de Calibración |
|---------|----------------------|
| `assistant_default` | Primeros 2-3s de audio de micrófono **mientras TTS reproduce** (mismo camino acústico) |
| `user_0` (Carlos) | Primeros 2-3s de voz captados por VAD |
| `user_1` (Luisa) | Primeros 2-3s de nueva voz detectada por VAD |

**Problema conocido (resuelto):** No usar `ref_audio` directamente como fingerprint. El camino altavoz → micrófono lo deforma. Ambos fingerprint (user y assistant) deben venir del micrófono.

**Calibración:**
- **Rolling update:** promedio exponencial de embeddings cada turno.
- **Dual comparison:** cada chunk compara `sim_user` vs `sim_assistant`.
- **Auto-enrollment:** si no hay match y confianza alta, crear `user_N`.
- **Threshold adaptativo:** aprende distancia entre user y assistant fingerprints.

## 2. Intent Router
Detecta intenciones de enrutamiento desde el STT.
- **Explícita:** "Quiero hablar con María" → `<<route_to:maria_tech>>`
- **Implícita:** LLM detecta contexto natural: Javier preguntó sobre legal → rutear a asistente legal.

## 3. Cambio de Asistente
Cambia `voice_clone_prompt` + `system_prompt` en tiempo real sin reiniciar el pipeline.
- `voice_map["maria"]` → `voice_clone_prompt_Maria.safetensors`
- `voice_map["javier"]` → `voice_clone_prompt_Javier.safetensors`

## 4. Dramaturgo Mode (Asistentes hablando entre ellos)
El LLM genera diálogo multi-speaker con tags XML:
```xml
<speaker:maria>Carlos, ¿qué opinas tú sobre esto?</speaker>
<speaker:javier>Desde mi perspectiva legal, lo mejor es revisar el contrato.</speaker>
<speaker:maria>Exacto Javier, revisémoslo juntos entonces.</speaker>
```
**Flujo TTS:**
1. Leer `<speaker:X>` → cambiar a voice_clone de X
2. Generar texto como audio
3. Repetir para siguiente tag de speaker
4. Cliente reproduce un único flujo de audio continuo

## Pipeline Modificado
```
Mic Audio → [VAD] + [SpeakerRegistry detect_speaker] → tag: speaker_id
       ↓
     [STT] → texto etiquetado + speaker_id
       ↓
     [LLM] → sesión compartida + speaker tags / intent routing
       ↓
     [Qwen3TTSHandler] → lee <<speaker:X>> → cambia voice_clone
       ↓
     [WebSocket] → único flujo de audio al cliente
```

## Hardware Budget (NVIDIA DGX Spark GB10 - 128GB Unificados)
| Componente | Memoria | Compartido? |
|-----------|---------|-------------|
| Gemma-4-12b (Q4) | ~7 GB | ✅ Sí |
| Qwen3-TTS 1.7B | ~4 GB | ✅ Sí |
| Parakeet 0.6B | ~2 GB | ✅ Sí |
| KV Cache (1 sesión) | ~1 GB | ✅ Compartido |
| 4 voice clones | ~40 MB | ✅ On demand |
| eCAPA-Voice (SpeechBrain) | ~100 MB | ✅ Compartido |
| **Total** | **~15 GB** | Sobran 113 GB |

## Roadmap (4 Fases)
1. **Fase 1:** `SpeakerRegistry` (detectar user vs. assistant)
2. **Fase 2:** Auto-enrollment + calibración continua
3. **Fase 3:** Intent routing + cambio de voz de asistente
4. **Fase 4:** Dramaturgo mode (asistentes hablan entre ellos)

## Notas
- Fingerprinting usa **eCAPA-Voice (SpeechBrain)** en GPU.
- Threshold es **adaptativo** basado en distancia entre embeddings user vs assistant.
- No se necesitan frameworks externos: pocas clases sobre el pipeline actual.
