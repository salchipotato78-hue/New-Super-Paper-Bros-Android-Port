# Android: reloj de pantalla, performance hint y resto de lo que tiene Wario

- **Reloj del juego enlazado a la pantalla (causa principal del "entrecortado" en Android).** En Android el lock de
  vsync estaba apagado (la rama no-Windows de `RefreshDisplayLockLocked` ponía `valid = false`), así que el juego iba
  a 60 Hz libres y los frames caían en cualquier punto del vblank. Ahora `GameActivity` manda el vblank de cada frame
  (`Choreographer`) y `vi.cpp` lo usa como fase del lock, igual que Wario. Con un flag `displayClockPending` para que
  pausar y reanudar rápido no duplique la cadena de callbacks.
- **Performance hint del hilo de juego (ADPF, Android 13+).** Reporta el trabajo de cada frame antes del vblank para que
  el planificador no baje el hilo a un núcleo lento. Wario tiene el mismo código protegido por `__ANDROID_API__ >= 33`,
  pero el nivel de API nativo sale de `minSdk` (29), así que ese bloque nunca se compila. Aquí se usa
  `__builtin_available(android 33, *)`, que decide en ejecución con `minSdk = 30`.
- **Resto de cambios de esta ronda:** semilla de shaders (migración v19→v20), worker de shaders de baja prioridad,
  resolución dinámica y térmico, PGO opcional, log de Aurora en `LOG_INFO`. Todo solo para Android. Ver las entradas
  anteriores.
- **Sin compilar aquí.** Verificado: balance de llaves de los archivos editados, sintaxis de los `.cpp` que dependen solo
  de cabeceras del runtime, scripts de semilla con datos sintéticos, workflow YAML y bash.

---

# Android: rendimiento (semilla de shaders, térmico, resolución dinámica, PGO)

- **Semilla de shaders obsoleta (causa de tirones).** La semilla tenía 1153 pipelines GX en la versión 19; el runtime
  espera la 20, así que se ignoraban y cada shader se compilaba en el teléfono al aparecer. Portada la migración de
  Wario (`pipeline_cache.cpp`): reescribe v19→v20 si el tamaño coincide. Activada en Android por defecto
  (`[video] migrate_stale_pipelines`). **No verificada en un teléfono**: revisa el log del primer arranque.
- **Compilación de shaders en Android.** Un único worker de baja prioridad en vez de todos los núcleos (compilar en
  paralelo quitaba CPU al hilo del juego). La cola de escritura se vacía al salir de la app.
- **Herramientas de semilla** `tools/android/check-pipeline-seed.py` y `promote-pipeline-seed.py` (de Wario, con rutas
  de SPM). Corregido el check: ahora compara cada tipo de shader con su propia versión (las filas Clear v3 se marcaban
  como obsoletas). Mismo fallo en la copia de Wario, sin corregir allí.
- **Resolución dinámica y térmico** portados de Wario: `dynamic_resolution.cpp`, `thermal_quality.cpp`, factores en
  `display_settings`, hook en `vi.cpp` en cada frame con pacing, JNI `nativeReportThermalHeadroom`, sondeo cada segundo
  en `GameActivity` (Android 12+). `thermal_quality.cpp` se compila con `-fno-finite-math-only`. El hook de `vi.cpp`
  usa `paceToRetrace` y no `paceThisFrame`: este último es falso justo en los frames que llegan tarde, y ahí es donde
  la resolución tiene que bajar. Los frames de menús y cinemáticas pasan por el mismo camino (`gx_copy.cpp`).
- **PGO** (opcional): CMake `MKW_PGO`, `android_pgo.cpp`, opción `pgo` del workflow y secreto `SPM_PGO_PROFILE_URL`.
- **Log de Aurora** en Android a `LOG_INFO` (antes `LOG_DEBUG` en cada frame). `SPM_LOG_DEBUG` lo vuelve a debug.
- **Sin compilar aquí** (sin NDK, Gradle, Dawn ni disco del juego). Verificado: sintaxis de los `.cpp` nuevos que
  dependen solo de cabeceras del runtime, scripts de semilla con datos sintéticos, workflow YAML y bash.

---

# Android: datos por secreto y workflow optimizado

- **Datos del juego por secreto, no por release.** `android-spm.yml` ya no usa el release `game-data`. Lee un zip
  del secreto `SPM_DATA_URL` (enlace de descarga directa) y `tools/android/extract-game-data.py` saca los archivos de
  la región, los verifica (SHA-256 de `main.dol` USA y que no sea la versión con el mod HQ) y para el job pronto si algo
  falla. Ver `android/README.md`.
- **Firma de release opcional.** Con `SPM_KEYSTORE_BASE64`, `SPM_KEYSTORE_PASSWORD`, `SPM_KEY_ALIAS` y
  `SPM_KEY_PASSWORD` cada APK se firma con la misma clave y actualiza al anterior sin desinstalar. Sin ellos sigue
  firmando con la clave debug, que cambia en cada run del runner.
- **ccache.** `CCACHE_COMPILERCHECK` fijado a la versión del NDK (la caché sobrevive a restaurar el NDK). Se guarda
  solo si no había nada que restaurar o si más del 3 % de las compilaciones falló (comparación sin división entera).
  ccache solo se instala si falta.
- **SDK.** Caché de platform, build-tools y cmake; `sdkmanager` solo corre si falta algo.
- **Paralelismo.** Trabajos calculados con núcleos y RAM (misma regla que el workflow de Wario).
- **Sin cambios a propósito:** la clave de la traducción sigue incluyendo `wiicompiled/runtime/src/**`. La traducción
  base lee ese código (ABI declaradas, efectos de funciones nativas, exclusiones), así que no se puede reutilizar tras
  un cambio en el runtime.
- **Limpieza.** Eliminados `tools/android/ci-prepare-inputs.py` (no lo usaba nada y documentaba el release) y dos
  archivos `.orig` sueltos.
- **Sin compilar aquí** (no hay NDK, Gradle ni el disco del juego): la primera ejecución del workflow dirá si algo falla.

---

# Diagnóstico de rendimiento (en curso)

Logs de cuatro partidas: todos los fotogramas lentos son de la escena `0xA418`, con `game` de 30 a 40 ms y `gx` a 0.
La interpolación 120 fps empeora el ritmo (`interpolation slots reduced to 0: 54/60 frames overran`), pero el juego
sigue lento sin ella. La línea de fotograma lento ahora incluye `copies X ms in N calls`, el tiempo dentro de
GXCopyDisp / GXCopyTex (vacían el FIFO en el hilo del juego).

---

# Idioma del juego en Android

El texto del diálogo sale de `msg/<idioma>/` y el idioma lo da `[game] language` en `Config.toml`. Sin esa clave el
runtime usa inglés (`msg/UK`), que es lo que aparece en el log del teléfono. Ahora el panel ⚙ tiene la fila
"Idioma del juego" (solo en la versión europea), que guarda el idioma en `Config.toml` y se aplica al reiniciar.
JNI: `nativeGameLanguage` y `nativeSetGameLanguage`.

---

# Opciones de gráficos del PC añadidas al Android

En el panel ⚙ de la app Android ahora hay tres filas, con los mismos ajustes que la ventana de opciones del PC
(`Graphics`):

- **Interpolación 120 fps (experimental):** `settings_overlay::SetFrameInterpolation120`.
- **V-Sync:** `settings_overlay::SetVSync` (ya existía en el runtime, sin UI en Android).
- **Filtro de copia:** `settings_overlay::SetDisableCopyFilter`.

Se guardan en `Config.toml` con las mismas claves que en PC (`frame_interpolation_fps`, `vsync`,
`disable_copy_filter`). JNI: `nativeApplyGraphicsSettings` y `nativeGraphicsSettings` en `android_bridge.cpp`.
No compilado aquí (sin NDK).

---

# Corrección del crash en el arranque (SIGSEGV en GXCopyDisp, DEMOInit)

## Causa real (sustituye al diagnóstico de `memInit` de abajo)

`PC=0` del volcado era un valor caducado ("ctx->pc may be stale"). El destino activo era `GXCopyDisp` (HLE), y el
log previo muestra `BeginAuroraFrame retry EXPIRED` y `Dropping command SetViewport`: Aurora nunca llegó a
empezar un frame. Aurora solo presenta si `g_surfaceReady` es true en Android, y eso lo activa el método
`SDLSurface.auroraNativeSetSurfaceReady`. El workflow descargaba el glue Java ORIGINAL de SDL y lo copiaba encima,
así que ese aviso no existía (tampoco la pila de 64 MB del hilo del juego). Resultado: la app siempre "en pausa",
todos los frames descartados, y `GXCopyDisp` llamaba a Aurora sin frame activo (lectura en 0x40).

## Cambios

1. `android/sdl-overlay/org/libsdl/app/{SDLSurface,SDLActivity}.java`: los dos archivos parcheados (antes solo en
   `wiicompiled/android`). El workflow los superpone tras descargar el SDL y comprueba que el parche está.
2. `gx_copy.cpp`: si no hay frame de Aurora activo, `GXCopyDisp`/`GXCopyTex` descartan la copia en vez de caerse.

No compilado aquí (sin NDK ni datos del juego): hay que relanzar el workflow.

---

# Cambios: crash de DEMOInit en la versión PAL (R8PP01)

## Diagnóstico

- El crash es `sigsegv` con PC=0. Desensamblando `DEMOInit` (PAL 0x801A9098) desde `mem1.bin` del log, la
  llamada que falla es `bl 0x801A5DCC` (`memInit` en `projects/spm/pal/MAP.txt`). El prólogo de `memInit` nunca
  se ejecutó: el salto cayó en una dirección nula.
- El camino de llamada directa lo genera el traductor como `MKW_STATIC_TRANSLATED_CALL(...)`. Un símbolo que no
  queda definido en el build da un puntero nulo. Esta causa raíz NO está confirmada: falta el log de
  `translate-europa` o el `build_shards` generado para ver qué símbolo se emitió para `memInit`.

## Cambios incluidos

1. **La traducción PAL pasaba sin lista de reanudables.** `tools/android/build-region.py` ahora pasa
   `projects/spm/pal/resumable_functions.inc` para `europa` (antes `None`).
2. **La lista de reanudables tenía direcciones USA.** Nuevo `projects/spm/pal/resumable_functions.inc` con las
   direcciones PAL, generado por `projects/spm/pal/tools/gen_pal_resumable.py` desde
   `resumable_functions.inc` y `addr_map.tsv`. Confirmadas en el MAP PAL: `__start`, `main` (0x8001DA60),
   `DEMODoneRender` (0x801A9590), `wiiDvdCheckThread` (0x801A898C).
3. **`save_state.cpp` incluía siempre la lista USA.** `make_pal_runtime.py` ahora reescribe el include a la lista PAL
   con una ruta relativa al propio archivo, sin depender de rutas `-I`.

## Pendiente (no incluido, a propósito)

- **Tres entradas sin dirección PAL verificada:** `fn_80305374`, `fn_803053C8` y `fn_8030862C` están comentadas
  como `UNVERIFIED`. Caen dentro de bloques `fn_` sin ancla y los candidatos del mapeo por vecino no son inicios de
  función en la memoria PAL. Hay que buscarlas en el dol PAL. Mientras tanto, el guardado de estado puede rechazarse
  en las cadenas que pasan por esas funciones.
- **`SYSCONF` ausente** (`NANDOpen FAILED ... SYSCONF`). No se siembra: el formato binario de SYSCONF no está
  verificado en el repo y un archivo mal formado sería peor que uno ausente.
- **Frames de GX descartados** (`BeginAuroraFrame retry EXPIRED`). Es un síntoma; no se tocó.
- **Limpieza pendiente:** `runtime/src/hle/sc.cpp` tiene comentarios residuales de NSMBW/MKW.

## Verificación

- Sintaxis de `build-region.py` y `make_pal_runtime.py` comprobada.
- El parser de `LoadList` del traductor (replicado) lee exactamente las cuatro direcciones confirmadas.
- NO se ha compilado el traductor, el runtime PAL ni el APK: no hay disco ni NDK en este entorno.
