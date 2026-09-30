# WebSocket de métricas del sistema
Status: partial
Last updated: 2026-09-19

## Objetivo

Sustituir el polling HTTP del frontend para CPU, GPU y VRAM por un canal WebSocket dedicado, manteniendo la frecuencia configurable del runtime.

## Problema y usuario objetivo

El panel lateral de AdVera consulta repetidamente `/api/system-metrics` aunque solo necesita recibir el snapshot más reciente. El usuario local que supervisa el runtime necesita métricas actualizadas sin ciclos HTTP recurrentes ni reconexiones manuales.

## Incremento minimo util

Emitir un snapshot inicial y snapshots posteriores por `/ws/system-metrics`, usando `metrics_refresh_interval_ms` como frecuencia. El frontend debe reconectar tras una desconexion y cerrar el canal al desmontarse.

## Alcance

- Añadir el WebSocket de métricas en FastAPI.
- Reutilizar el contrato actual de CPU, GPU y VRAM.
- Mantener el ajuste runtime de 5 a 60 segundos.
- Reemplazar el timer HTTP del frontend por un cliente WebSocket con reconexion.
- Mantener el endpoint HTTP existente como fallback operativo.

## Criterios de aceptacion

- Al conectar, el WebSocket entrega inmediatamente un snapshot valido.
- Entrega snapshots con el intervalo configurado y usa cambios del intervalo en nuevas esperas.
- Un cierre o error del canal provoca reconexion con backoff sin bloquear la interfaz.
- El frontend no ejecuta polling HTTP de `/api/system-metrics`.
- El canal se cierra al desmontar la aplicacion.
- CPU, GPU y VRAM conservan el contrato y los valores no se almacenan como datos de reuniones.

## Estados y fallos

- Conectado y recibiendo snapshots.
- Reconexion tras cierre inesperado.
- Error de medicion: el canal conserva la conexion si es posible y envia el snapshot disponible del backend.
- Cierre limpio al apagar o desmontar el cliente.

## Datos y procedencia

Las metricas son telemetria efimera del proceso local, calculada por `psutil` y PyTorch cuando esta disponible. No contienen audio, transcripciones, secretos ni contenido de reuniones; no se persisten.

## Supuestos y preguntas abiertas

- El intervalo runtime continua restableciendose al reiniciar el backend.
- El endpoint HTTP se conserva para compatibilidad y diagnostico.
- No se requiere autenticacion adicional mientras el runtime siga siendo local.

## Estado de implementacion

Implementado en backend y frontend.

## Validacion

- `backend/tests/test_system.py` y `backend/tests/test_settings.py`: 8 pruebas pasando.
- Ruff pasa para los archivos backend modificados.
- Diagnosticos de VS Code sin errores nuevos en `frontend/src/App.tsx`, `backend/app/system.py` y `backend/tests/test_system.py`.
- El build frontend no se pudo ejecutar porque Node.js/npm no estan disponibles en `PATH`.

## Riesgos

Multiples pestañas mantienen una conexion independiente y cada una solicita sus propios snapshots. El rango minimo de 5 segundos limita el coste de medicion.

## Proxima accion

Ejecutar `npm run build` en un entorno con Node.js instalado y verificar la reconexion desde el navegador.
