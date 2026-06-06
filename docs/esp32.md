# ESP32 Voice Agent

Idea principal: Crear un hardware pequeño y económico con un micrófono y un altavoz para interactuar en tiempo real con el servidor de voz.

## 1. Arquitectura General

```
Micrófono I2S → ESP32 (captura PCM 16kHz) → WebSocket → Servidor Python (VAD → STT → LLM → TTS) → WebSocket → ESP32 (reproduce PCM) → Altavoz
```

## 2. Hardware Recomendado

| Componente | Recomendación | Notas |
|---|---|---|
| **Placa** | ESP32-S3 (recomendado) o ESP32-WROOM | Mejores prestaciones de procesamiento y memoria. |
| **Micrófono** | INMP441, MSM261S4030H, MP34DT01 | Interfaz I2S digital, muy superior al ADC análogo. |
| **Altavoz / Amplitificación** | MAX98357A/B (Clase D, I2S) | Permite altavoces potentes con calidad aceptable. Alternativa más simple: PWM + amp básico. |
| **Alimentación** | Fuente externa | El USB a veces no llega para alimentar placa + amplificador + altavoz. |

## 3. Interfaces de Audio (Entrada y Salida)

Para lograr una comunicación limpia, estable y de alta calidad, se utiliza el estándar **I2S (Inter-IC Sound)** tanto para la entrada como para la salida.

### 3.1. Entrada (Micrófono)
Es fundamental elegir el tipo de micrófono adecuado para la calidad de la conversación.

1. **Micrófonos Analógicos (ADC):**
   - **Ejemplos:** Micrófono electret básico.
   - **Funcionamiento:** Generan una salida de voltaje variable. El ESP32 debe usar un convertidor ADC interno.
   - **Contras:** Calidad inferior, susceptible a ruido y estática, y consume ciclos de CPU para la conversión.
2. **Micrófonos Digitales (I2S):** (Recomendado)
   - **Ejemplos:** INMP441, MSM261S4030H, MP34DT01.
   - **Funcionamiento:** El micrófono ya lleva un chip ADC integrado.
   - **Ventajas:** Envía datos puros (0s y 1s) directamente al controlador I2S. Es más limpio, estable, sin ruido y menos costoso para la CPU.

*Nota: En este proyecto buscaremos maximizar la calidad de entrada para que el VAD y el STT funcionen correctamente.*

### 3.2. Salida (Altavoz)
Al igual que en la entrada, el I2S se utiliza para alimentar directamente a un amplificador digital.

1. **Salida Analógica (PWM/ADC):**
   - **Funcionamiento:** El ESP32 envía una señal de modulación por ancho de pulsos (PWM) que imita una onda de audio.
   - **Contras:** Suele aportar "chispoteo" eléctrico, requiere un filtro RC y distorsiona a altos volúmenes.
2. **Amplificadores Digitales (I2S):** (Recomendado)
   - **Ejemplos:** Amplificadores de Clase D como el **MAX98357A** o **MAX98357B**.
   - **Funcionamiento:** Recibe el flujo digital I2S del ESP32 y lo convierte en una señal de potencia para el altavoz.
   - **Ventajas:** Respuesta de frecuencia plana, ausencia de ruidos de fondo de PWM, alta eficiencia energética y mayor potencia de salida.

## 4. Flujo de Datos

1. **Captura:** El micrófono digital I2S envía audio PCM al ESP32 a 16kHz, 16 bits, mono.
2. **Streaming de entrada:** El ESP32 envía los "chunks" (típicamente 1024 bytes) por WebSocket al servidor.
3. **Procesamiento:** El servidor Python (VAD → STT → LLM → TTS) procesa y genera la respuesta de voz.
4. **Streaming de salida:** El servidor envía el audio resultante (PCM 16kHz) por WebSocket.
5. **Reproducción:** El ESP32 recibe los datos y los envía al amplificador I2S para el altavoz.

## 5. Integración con el Servidor

| Modo servidor | Protocolo | Complejidad en ESP32 | Estado |
|---|---|---|---|
| `websocket` (Modo 3) | Bin + JSON | **Baja**: Solo envía/recibe chunks de bytes | ✅ Puntos de partida ideal |
| `realtime` (Modo 4) | OpenAI Realtime API (Eventos JSON) | **Media/Alta**: Requiere parsear y responder a eventos estructurados | Evolución futura |

*Se recomienda comenzar con el modo `websocket` (`--mode websocket --ws_host 0.0.0.0 --ws_port 8765`). Es simple y permite validar el flujo completo de audio sin complicarse con eventos.*

## 6. Notas Actuales

- El servidor ya soporta fingerprinting server-side (SpeechBrain eCAPA-Voice reservado para ESP32)
- Web client usa `isPlaying` mic mute; ESP32 usará fingerprinting digital I2S (sin eco de altavoz)
- Modo `websocket` es el más simple para empezar

## 7. Próximos Pasos

- [ ] Investigar librerías específicas (Arduino `I2S` y `WebSockets`)
- [ ] Definir conexión física (ESP32-S3 recomendado, pines I2S)
- [ ] Implementar captura PCM y envío por WebSocket
- [ ] Implementar reproducción I2S/PWM
- [ ] Prueba de concepto: bucle de audio (eco local)
- [ ] Conectar con servidor Python en modo `websocket`
- [ ] Optimizar buffers y gestión de memoria
