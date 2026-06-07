# Multi-User & Multi-Assistant Architecture

## Estado
✅ **Fases 1, 3, y 4 implementadas.** Speaker identification, routing por tags `<<route_to:X>>`, Dramaturgo Mode (multi-assistente en una respuesta). Fase 2 (auto-enrollment) pendiente.

## Concepto Fundamental: Usuario vs. Asistente

**Son entidades DISTINTAS. Nunca se mezclan.**

| Entidad | Origen | Función | Tag | Ejemplo |
|---------|--------|---------|-----|---------|
| **Usuario** | Hardware (Micrófono) | Persona que está hablando. Identificada por fingerprinting de voz. | `<<speaker:carlos>>` | `<<speaker:carlos>> ¿Cómo optimizar este código?` |
| **Asistente** | Software (Sistema) | Personalidad que responde. Tiene propia voz, rol y sistema prompt. | `<<route_to:dev_jefe>>` | `<<route_to:dev_jefe>> Claro Carlos, veamos la complejidad...` |

**REGLAS CRÍTICAS:**
- `<<speaker:X>>` → **NUNCA** es un asistente. Siempre un usuario real.
- `<<route_to:X>>` → **NUNCA** es un usuario. Siempre un asistente del sistema.
- El sistema **Jamás** replica la voz de un usuario ("no es mirror voice").
- Los IDs válidos para `<<route_to:X>>` son: `default`, `dev_jefe`, `abogado`.

## Goal
Soportar múltiples usuarios y múltiples asistentes en una sesión compartida, con reconocimiento de voz y enrutamiento dinámico.

## Core Concept: "Shared Room" (Sala Compartida)
- **Un solo KV Cache:** toda la conversación se mantiene en un solo hilo. No hay aislamiento de sesiones.
- **Speaker Registry:** fingerprinting en tiempo real para identificar qué usuario habla.
- **Dynamic Routing:** el LLM decide qué asistente responde según el contexto/intención del usuario.
- **Dramaturgo Mode:** los asistentes pueden hablar entre ellos en secuencia, controlados por el LLM.

## Flujo End-to-End

### Escenario Normal: Un usuario habla, un asistente responde

```
Mic Audio → VAD (Silero, min_silence_ms=600)
  └─→ SpeechStoppedEvent
        └─→ SpeakerRegistry.identify(array) → user_id="carlos"
              └─→ SpeechStoppedEvent(speaker_id="carlos")
                    └─→ audio.py: on_speech_stopped()
                          └─→ st.last_speaker_id = "carlos"
                                └─→ _on_transcription_completed()
                                      └─→ User msg: "<<speaker:carlos>> ¿cómo optimizo este código?"
                                            └─→ LLM (System Prompt lista asistentes disponibles)
                                                  └─→ Response: "<<route_to:dev_jefe>> Claro Carlos, aquí el cuello de botella está en la complejidad O(n²)..."
                                                        └─→ [Qwen3TTSHandler] parse_route_segments()
                                                              ├─→ Segmento 1: (route_to="dev_jefe", text="Claro Carlos...")
                                                              ├─→ _apply_route_voice("dev_jefe") → voice_clone_prompt de dev_jefe
                                                              ├─→ TTS → audio chunks (voz de dev_jefe)
                                                              └─→ _restore_default_voice() → voz por defecto
                                                                    └─→ WebSocket → Cliente
```

### Escenario Dramaturgo: Dos asistentes hablan entre ellos

```
Mic Audio → VAD → identify() → usuario: "maria"
  └─→ User msg: "<<speaker:maria>> Explicadme la situación"
        └─→ LLM genera:
              "<<route_to:dev_jefe>> El código tiene un bug crítico. 
               <<route_to:abogado>> Eso podría derivar en una demanda. 
               <<route_to:dev_jefe>> ¿Entonces lo parchamos ya?"
                    └─→ [Qwen3TTSHandler] parse_route_segments()
                          ├─→ Segmento 1: (route_to="dev_jefe", "El código tiene un bug crítico")
                          │     └─→ _apply_route_voice("dev_jefe") → audio A
                          ├─→ Segmento 2: (route_to="abogado", "Eso podría derivar en una demanda")
                          │     └─→ _apply_route_voice("abogado") → audio B
                          └─→ Segmento 3: (route_to="dev_jefe", "¿Entonces lo parchamos ya?")
                                └─→ _apply_route_voice("dev_jefe") → audio C
                                      └─→ Cliente escucha: "Dev dice esto... Abogado dice esto... Dev pide confirmación"
```

## Asistentes Disponibles

Los asistentes están definidos en el System Prompt (`LLM/voice_prompt.py`):

| ID | Persona | Trigger |
|----|---------|---------|
| `default` | Polite, general purpose | Preguntas ordinarias, saludos, small talk |
| `dev_jefe` | Senior developer, directo, técnico | Código, bugs, arquitectura, optimización |
| `abogado` | Legal advisor, prudente | Contratos, derechos, disputas, términos |

### Personalización

Para añadir un nuevo asistente, edita `VOICE_SYSTEM_PROMPT_SPEAKER_ROUTING` en `LLM/voice_prompt.py` y registra su voz:

```python
tts_handler.register_voice("nuevo_assistente", "/path/to/audio.wav")
```

## 1. Speaker Registry (`SpeakerRegistry`)

Base de datos de fingerprints de todos los **usuarios**. Usa **eCAPA-Voice (SpeechBrain)** para generar embeddings de voz.

### Archivo: `VAD/speaker_registry.py`

```python
class SpeakerRegistry:
    def __init__(self, device: str = "cuda")
    def register(self, user_id: str, audio_chunk: np.ndarray)
    def identify(self, audio_chunk: np.ndarray) -> Optional[str]
    def has(self, user_id: str) -> bool
```

### Uso básico

```python
from speech_to_speech.VAD.speaker_registry import SpeakerRegistry

registry = SpeakerRegistry(device="cuda")

# Calibrar usuario (solo input de micrófono, NUNCA altavoz→micrófono)
registry.register("carlos", mic_audio_chunk)  # 2-3 seg de audio 16kHz mono

# Identificar: retorna user_id o None si no hay match
speaker_id = registry.identify(audio_chunk)
# → "carlos" con similitud ≥ threshold (default 0.5)
```

### Calibración automática

**Rolling update:** promedio exponencial (α=0.3) del embedding al registrar. Mejora la precisión con cada turn.

**Threshold adaptativo** (pendiente implementación): aprender distancia entre embeddings para ajustar `self.threshold`.

### Problema conocido (resuelto)

No usar `ref_audio` directamente como fingerprint. El camino altavoz → micrófono lo deforma. **Los fingerprints deben venir del micrófono.**

## 2. Integración en VAD Handler

### Archivo: `VAD/vad_handler.py`

El handler acepta `speaker_registry` como parámetro en `setup()`:

```python
def setup(
    self,
    should_listen: Event,
    ...
    speaker_registry: SpeakerRegistry | None = None,
) -> None:
    ...
    self.speaker_registry = speaker_registry
```

Cuando VAD detecta silencio tras un turno de habla, ejecuta `identify()` automáticamente:

```python
# Al final de un turn (min_silence_ms de silencio)
speaker_id = None
if self.speaker_registry:
    speaker_id = self.speaker_registry.identify(array)
self.text_output_queue.put(
    SpeechStoppedEvent(
        duration_s=duration_ms / 1000.0,
        audio_end_ms=end_ms,
        speaker_id=speaker_id  # ← nuevo campo
    )
)
```

### Archivo: `pipeline/events.py`

```python
class SpeechStoppedEvent(PipelineEvent):
    type: Literal["speech_stopped"] = "speech_stopped"
    duration_s: float = 0.0
    audio_end_ms: int = 0
    turn_id: str | None = None
    turn_revision: int | None = None
    speaker_id: str | None = None  # ← NUEVO: ID del usuario que habló
```

## 3. Propagación al LLM

### Archivo: `api/openai_realtime/handlers/audio.py`

`on_speech_stopped()` almacena `speaker_id` en `ConnState`:

```python
def on_speech_stopped(self, conn_id: str, event: SpeechStoppedEvent) -> list[ServerEvent]:
    st = self._state(conn_id)
    if event.duration_s:
        st.input_audio_duration_s = event.duration_s
    st.last_speaker_id = event.speaker_id  # ← ID del USUARIO
    ...
```

### Archivo: `api/openai_realtime/service.py`

```python
class ConnState(BaseModel):
    ...
    last_speaker_id: str | None = None  # ← ID del USUARIO que habló
```

`_on_transcription_completed()` prepande tag `<<speaker:X>>` (usuario) al mensaje:

```python
speaker_prefix = f"<<speaker:{st.last_speaker_id}>> " if st.last_speaker_id and transcript else ""
full_transcript = speaker_prefix + transcript
```

Resultado: `<<speaker:carlos>> ¿cómo optimizo este código?` se agrega al chat history del LLM.

## 4. System Prompt con Instrucciones de Routing

### Archivo: `LLM/voice_prompt.py`

Sección `VOICE_SYSTEM_PROMPT_SPEAKER_ROUTING` inyectada automáticamente:

```
## Speaker Identification & Routing (read this section carefully)

### Speaker Identification (Input)
When a user message begins with `<<speaker:X>>`, "X" is the identified USER who is
speaking in the room. Use this name to personalize your response.

### Assistant Routing (Output)
The system has multiple assistants, each with its own role, personality, and voice.
Use `<<route_to:X>>` tags at the start of your spoken text to decide which assistant responds.

Available Assistants:
- `default` — General purpose, polite, helpful.
- `dev_jefe` — Senior developer persona, technical, focused on code quality.
- `abogado` — Legal advisor persona, cautious, precise.

CRITICAL RULES:
- `<<route_to:X>>` NEVER uses a user's name. Only assistant IDs.
- The system will NEVER mirror back a user's voice.
```

## 5. Dynamic Voice Switching en TTS

### Archivo: `TTS/qwen3_tts_handler.py`

### Métodos clave

```python
def register_voice(self, speaker_id: str, ref_audio_path: str | Path) -> None:
    """Registrar una voz de asistente en el voice_map."""

def _apply_route_voice(self, assistant_id: str) -> None:
    """Cambiar temporalmente a la voz del asistente."""

def _restore_default_voice(self) -> None:
    """Volver a la voz por defecto."""

def _parse_route_segments(self, text: str) -> list[tuple[str | None, str]]:
    """Dramaturgo Mode: parsea TODOS los <<route_to:X>> y retorna segmentos."""
```

### `_parse_route_segments` (Dramaturgo Mode)

```python
def _parse_route_segments(self, text: str) -> list[tuple[str | None, str]]:
    """Divide texto en segmentos por <<route_to:X>> tags.
    
    Input: "<<route_to:dev> Hola <<route_to:legal> y adiós"
    Return: [("dev", "Hola"), ("legal", "y adiós")]
    """
```

### Process flow (con Dramaturgo Mode)

```python
def process(self, tts_input: TTSIn) -> Iterator[TTSOut]:
    ...
    text = coalesced_text or "Hello."

    # 1) Parse ALL route segments
    segments = self._parse_route_segments(text)
    # [("(dev_jefe", "Claro Carlos..."), ("abogado", "Eso podría...")]

    # 2) Generate audio per segment sequentially
    for route_target, segment_text in segments:
        if route_target and route_target in self._voice_map:
            self._apply_route_voice(route_target)

        audio_iter = self._process_voice_clone(segment_text)
        for chunk in audio_iter:
            yield chunk

        if route_target:
            self._restore_default_voice()
```

### Voice map

```python
self._voice_map: dict[str, Any] = {
    "dev_jefe": <voice_clone_prompt_dev>,
    "abogado": <voice_clone_prompt_legal>,
    ...
}
self._default_voice_clone_prompt = <voice_clone_prompt_default>
```

## 6. Auto-Creation de Speaker Registry en Pipeline

### Archivo: `s2s_pipeline.py` → `_build_realtime_pipeline_unit()`

```python
vars(vad_kw)["speaker_registry"] = SpeakerRegistry(device=module_kwargs.device)
```

Cada pipeline unit crea su propia `SpeakerRegistry` con el device del módulo (`cuda`, `mps`, `cpu`).

## 7. Registro de Voces

### De Usuarios (Input)

```python
from speech_to_speech.VAD.speaker_registry import SpeakerRegistry

registry = SpeakerRegistry(device="cuda")
registry.register("carlos", mic_audio_chunk)
```

### De Asistentes (Output / TTS)

```python
# El TTS handler obtiene el voice_clone_prompt desde ref_audio
tts.register_voice("dev_jefe", "/path/to/dev_voice.wav")
tts.register_voice("abogado", "/path/to/legal_voice.wav")
```

### Plan para auto-enrollment (usuarios)

Cuando `SpeakerRegistry.identify()` retorna `None` (desconocido), se puede:
1. Registrar automáticamente como `user_N` con `ref_audio` del turno
2. Solicitar al usuario el nombre del participante
3. No crear voice clone automáticamente (eso sería mirror voice, no implementado)

## Pipeline Completo

```
Mic Audio
  └─→ [VAD Handler] (Silero VAD, min_silence_ms=600)
        ├─→ SpeechStartedEvent
        ├─→ SpeechStoppedEvent
        │     └─→ [SpeakerRegistry] identify(array) → user_id="carlos"
        │           └─→ SpeechStoppedEvent(speaker_id="carlos")   # USUARIO
        │                 └─→ audio.py: on_speech_stopped()
        │                       └─→ st.last_speaker_id = "carlos"
        │                             └─→ _on_transcription_completed()
        │                                   ├─→ Chat: "<<speaker:carlos>> ¿cómo optimizo?"  # TAG USUARIO
        │                                   └─→ GenerateResponseRequest
        │                                         └─→ [LLM Handler] (responses-api / llama.cpp)
        │                                               └─→ LLM aplica System Prompt (lista asistentes)
        │                                                     └─→ Response: "
        │                                                          <<route_to:dev_jefe> El bug está en O(n²)...
        │                                                          <<route_to:abogado> Y eso implica responsabilidad contractual..."
        │                                                               # TAGS ASISTENTE
        │                                                                    └─→ [LMOutputProcessor]
        │                                                                          └─→ TTSInput
        │                                                                                └─→ [Qwen3TTSHandler]
        │                                                                                  ├─→ _parse_route_segments()
        │                                                                                  │   → [("dev_jefe", "El bug está en O(n²)..."),
        │                                                                                  │      ("abogado", "Y eso implica...")]
        │                                                                                  ├─→ Loop: segmento 1 → dev_jefe voice → audio
        │                                                                                  ├─→ Loop: segmento 2 → abogado voice → audio
        │                                                                                  └─→ Yield chunks secuenciales
        │                                                                                        └─→ [WebSocket] → Cliente
```

## Hardware Budget (NVIDIA DGX Spark GB10 - 128GB Unificados)

| Componente | Memoria | Compartido? |
|-----------|---------|-------------|
| Gemma-4-12b (Q4) | ~7 GB | ✅ Sí |
| Qwen3-TTS 1.7B | ~4 GB | ✅ Sí |
| Parakeet 0.6B | ~2 GB | ✅ Sí |
| KV Cache (1 sesión) | ~1 GB | ✅ Compartido |
| 3+ voice clones (asistentes) | ~40 MB | ✅ On demand |
| eCAPA-Voice (SpeechBrain) | ~100 MB | ✅ Compartido |
| **Total** | **~15 GB** | Sobran 113 GB |

## Archivos Modificados / Nuevos

| Archivo | Tipo | Descripción |
|---------|------|-------------|
| `VAD/speaker_registry.py` | Existente | eCAPA-Voice fingerprinting |
| `VAD/vad_handler.py` | Modificado | `speaker_registry` en `setup()`, `identify()` al final de turn |
| `pipeline/events.py` | Modificado | `SpeechStoppedEvent.speaker_id` (usuario) |
| `arguments_classes/vad_arguments.py` | Modificado | `speaker_registry: Optional["SpeakerRegistry"]` |
| `s2s_pipeline.py` | Modificado | `SpeakerRegistry()` en `_build_realtime_pipeline_unit()` |
| `api/openai_realtime/service.py` | Modificado | `ConnState.last_speaker_id`, `<<speaker:USER>>` en user messages |
| `api/openai_realtime/handlers/audio.py` | Modificado | `st.last_speaker_id = event.speaker_id` |
| `LLM/voice_prompt.py` | Modificado | `VOICE_SYSTEM_PROMPT_SPEAKER_ROUTING` con lista de asistentes |
| `TTS/qwen3_tts_handler.py` | Modificado | `register_voice()`, `_parse_route_segments()`, Dramaturgo loop |

## Roadmap (Fases)

1. ✅ **Fase 1:** `SpeakerRegistry` integrada en VAD → `user_id` en chat history → `<<speaker:carlos>>`
2. 🔄 **Fase 2:** Auto-enrollment + calibración continua (pendiente)
3. ✅ **Fase 3:** Intent routing (`<<route_to:ASSISTANT>>`) + cambio de voz en TTS
4. ✅ **Fase 4:** Dramaturgo mode (`_parse_route_segments()`, loop secuencial por asistentes)

## Notas

- Fingerprinting usa **eCAPA-Voice (SpeechBrain)** en GPU.
- Threshold actual: **0.5 (fijo)**. Pendiente adaptativo.
- Tags (`<<speaker:X>>` usuarios, `<<route_to:X>>` asistentes) se insertan directamente en el flujo.
- Dramaturgo Mode: TTS itera por todos los segmentos secuencialmente, cambiando voz por cada uno.
- La voz se restaura automáticamente después de cada segmento con routing.
- El system prompt lista explícitamente los asistentes disponibles con sus roles.
- **NO ES MIRROR VOICE:** un usuario habla, un asistente responde con su propia voz.
