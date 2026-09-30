# Intervalo de actualización de system-metrics
Status: partial
Last updated: 2026-09-19

## Objetivo

Permitir configurar desde Ajustes la frecuencia con la que AdVera actualiza CPU, GPU y VRAM en la tarjeta de runtime.

## Alcance

- Opciones de 5, 10, 30 y 60 segundos.
- Persistencia en el contrato de configuración runtime existente.
- Aplicación inmediata del nuevo intervalo al polling del frontend.
- Valor por defecto de 5 segundos.

## Criterios de aceptación

- Ajustes muestra y permite cambiar el intervalo.
- Guardar devuelve y conserva el valor seleccionado.
- El polling consulta `/api/system-metrics` usando el intervalo guardado.
- Cambiar el intervalo reinicia el polling sin duplicar ciclos.
- Un valor inválido es rechazado por el backend.
- Si las métricas fallan, la configuración permanece disponible.

## Estado de implementación

Implementado en backend y frontend.

## Decisiones

- Se reutiliza `/api/settings` y su alcance runtime local.
- El intervalo se expresa en milisegundos en la API y en segundos en la interfaz.
- El frontend usa `setInterval` y lo recrea cuando cambia la configuración.

## Validación

- `backend/tests/test_settings.py`: 5 pruebas pasando.
- Diagnósticos de VS Code sin errores en backend y frontend.
- Comprobación manual: Ajustes muestra el selector con el valor guardado de 5 segundos.
- El endpoint `/api/system-metrics` responde correctamente en el contenedor activo.

## Riesgos

- El valor persistido actualmente es runtime y se restablece al reiniciar el backend.
- Intervalos demasiado cortos pueden aumentar la carga del API; el backend limita el rango a 5-60 segundos.

## Próxima acción

Revisar el intervalo elegido durante pruebas de carga si se habilitan frecuencias menores a 5 segundos.
