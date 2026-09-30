# Biblioteca de reuniones
Status: partial
Last updated: 2026-09-19

## Objetivo

Dar a la persona usuaria un espacio para consultar y gestionar las reuniones guardadas en AdVera.

## Alcance

- Listar reuniones ordenadas de la más reciente a la más antigua por fecha y hora de creación.
- Mostrar nombre, fecha y hora, estado y número de asistentes.
- Crear una reunión con nombre obligatorio.
- Eliminar una reunión con confirmación.
- Abrir la vista de detalle de una reunión.
- Mantener la reunión seleccionada en una URL directa y restaurarla tras refrescar.
- Cubrir estados de carga, vacío y error.

## Criterios de aceptación

- La página muestra las reuniones en orden descendente por `created_at`.
- Cada fila muestra las cuatro columnas solicitadas.
- Una lista vacía ofrece una acción visible para crear una reunión.
- Crear una reunión válida la añade al listado y permite abrir su detalle.
- El nombre es obligatorio y los errores de creación se muestran sin perder la entrada.
- Eliminar requiere confirmación; cancelar no cambia el listado y confirmar retira la reunión.
- Los errores de carga y eliminación se muestran al usuario.
- Abrir una reunión navega a `/meetings/<id>` y refrescar conserva esa vista.
- El botón lateral y el breadcrumb vuelven a `/meetings`.

## Estado de implementación

Implementado en la pantalla principal de reuniones, incluyendo navegación persistente por URL.

## Decisiones

- Se reutilizan los endpoints existentes de reuniones.
- El backend sigue siendo la fuente de verdad para orden, estado y fecha de creación.
- El modelo actual no tiene una entidad de asistentes; el contador se muestra como cero hasta que exista una fuente explícita de participantes.
- Se usa `history.pushState` para evitar introducir un router adicional en esta aplicación de una sola pantalla.

## Archivos previstos

- `frontend/src/App.tsx`
- `frontend/src/styles.css`

## Validación

- Diagnósticos de VS Code sin errores en `frontend/src/App.tsx` y `frontend/src/styles.css`.
- Verificación manual en navegador: abrir una reunión cambia la URL y F5 restaura el detalle.
- El build y las pruebas E2E quedan pendientes porque el entorno actual no tiene `node`, `npm`, `pnpm`, `yarn` ni `tsc` disponibles.

## Riesgos

- El contador de asistentes no puede inferirse de transcript provisional ni de texto libre.
- La eliminación actual es permanente y no elimina necesariamente artefactos asociados fuera de la entidad de reunión.

## Próxima acción

Ejecutar `npm run build` y `npm run test:e2e` en un entorno con Node.js instalado.
