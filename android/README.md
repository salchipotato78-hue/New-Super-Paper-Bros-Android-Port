# Super Paper Mario — Android

APK de **Super Paper Mario** (Wii) para Android, compilado por **GitHub Actions**. Hay dos versiones, **USA**
(R8PE01 rev. 0) y **Europa** (R8PP01). Cada APK es de una sola versión: eliges la región al lanzar el workflow. Usa el mismo
runtime que el resto del repositorio (WiiCompiled), con:

- **Ultrawide sin estirar:** por defecto el juego ocupa toda la pantalla con su proporción (`aspect_mode = 2`).
  Desde el menú ⚙ puedes pasar a 16:9 o 4:3.
- **Controles táctiles editables:** cada botón se puede **mover**, cambiar de **tamaño** (50–200 %) y de
  **opacidad** (20–100 %). Se guardan en el teléfono. ⚙ (arriba a la izquierda) → editar; "Restablecer" vuelve
  a la disposición inicial.
- **Arte propio** de `paper-mario-touch` (salto, martillo, lanzar objeto, Pixl, interactuar, menú y palanca con
  la moneda), y el icono sale de la portada.

El juego **no está en el repositorio**. Cada uno usa sus propios datos.

## Qué necesita el workflow

- **En el repositorio:** el código tal cual está en el zip, con `.github/workflows/android-spm.yml`.
- **En GitHub (una vez):** el release `game-data` con estos archivos, con esos nombres exactos:
  - `main.dol` y `relF.bin` del disco **USA** (siempre; para Europa también hacen falta, porque el runtime europeo
    se genera a partir de ellos, igual que en el PC).
  - `main-eu.dol` y `relF-eu.bin` del disco **europeo**, solo si compilas la región Europa.
- **Nada más:** el SDL de Java lo descarga el propio workflow, y el código traducido se genera en la ejecución.
- **No hace falta** el zip completo del juego: ese solo va al teléfono.

## Región

Al lanzar el workflow eliges **usa** o **europa**. El APK comprueba el zip contra esa región: un zip USA en un APK
europeo (o al revés) se rechaza con un mensaje claro. Para jugar las dos versiones, compila un APK por región.

## 1. Preparar tus datos (una vez)

Necesitas tu disco de Super Paper Mario USA (R8PE01, revisión 0). Saca de él:

| Archivo | Dónde está en el disco | Para qué |
|---|---|---|
| `main.dol` | `sys/main.dol` (USA) | Compilar el APK (SHA-256 `0d7487bc…`) |
| `relF.bin` | `files/rel/relF.bin` (USA) | Compilar el APK (se enlaza en CI) |
| `main-eu.dol` | `sys/main.dol` (Europa, original sin el mod HQ) | Solo región europea |
| `relF-eu.bin` | `files/rel/relF.bin` (Europa) | Solo región europea |

**En GitHub:** crea un *release* llamado **`game-data`** en tu fork y sube esos dos archivos con esos nombres exactos.
Son pocos MB, así que no pasan el límite de GitHub.

**En el teléfono:** haz un `.zip` de la carpeta **DATA** de tu disco de la **misma región** que el APK (debe tener
`sys/main.dol`, `sys/boot.bin`, `sys/fst.bin` y `files/`). Es el zip completo, no el release.

## 2. Compilar el APK

Pestaña **Actions** → **Android APK (Super Paper Mario)** → **Run workflow** → elige la **región**. Al terminar, el APK
está en **Releases** de tu repositorio, con el nombre `apk-<región>-run<número>`, como archivo `super-paper-mario-<región>.apk`
(sin zip, listo para descargar en el PC o el móvil). El artefacto del run también sigue disponible. La primera vez tarda bastante (traducir el juego); las siguientes van más rápido por la caché.

## 3. Instalar y jugar

1. Instala el APK (permite instalar apps desconocidas). Está firmado con la clave de depuración, para uso personal.
2. Abre **Super Paper Mario** y pulsa **Elegir zip de datos**. El zip se descomprime una vez y se comprueba.
3. Pulsa jugar. Para cambiar los controles, ⚙ → **Editar controles**.

## Controles por defecto

Los botones y su entrada del mando Wii (sideways). Está en `TouchOverlay.contribution()`, si quieres cambiarlos:

| Botón (arte) | Wii Remote | Qué hace (tabla del juego) |
|---|---|---|
| Palanca (moneda sobre pergamino) | D-pad | Mover |
| Saltar (Mario saltando) | 2 | Saltar |
| Martillo | 1 | Habilidad especial del personaje actual |
| Interactuar (guante fantasma) | A | Confirmar / interactuar / levantar |
| Lanzar objeto (seta) | B | Lanzar o soltar el objeto que llevas |
| Píxels | + | Menú de selección de Píxels |
| Menú (pergamino) | − | Menú principal: inventario, cartas, mapa |
| Apuntar (puntero de Tippi, la mano) | Puntero del mando | Un dedo sobre cualquier zona libre de la pantalla apunta; mantenerlo pulsado es A, como el clic del ratón |

> El mapeo sigue la tabla de controles de Super Paper Mario. Los botones se cambian en `TouchOverlay.contribution()`.

## Estructura

| Ruta | Contenido |
|---|---|
| `android/app/src/main/java/com/superpapermario/SetupActivity.java` | Pantalla de inicio: elegir el zip de datos y abrir el juego |
| `…/DataImporter.java` | Descomprimir, validar (R8PE01 rev. 0 y `main.dol`) y escribir `Config.toml` (sin Android) |
| `…/GameActivity.java` | Actividad del juego (extiende `SDLActivity`), formato de pantalla y overlay |
| `…/TouchOverlay.java` | Controles táctiles, edición y envío al runtime |
| `…/SpmApplication.java` | Desempaqueta el runtime y guarda el último error |
| `android/app/src/main/res/drawable-nodpi/` | Arte de `paper-mario-touch` |
| `wiicompiled/runtime/src/android/android_bridge.cpp` | JNI: `nativeSetTouchState`, `nativeApplyDisplaySettings` |
| `tools/android/build-region.py` | Prepara las entradas de cada región y traduce (USA o Europa) |
| `.github/workflows/android-spm.yml` | El workflow que compila el APK |

Para la lógica de importación hay una prueba que corre en el PC, sin Android:

```bash
javac -d out android/app/src/main/java/com/superpapermario/DataImporter.java android/tests/com/superpapermario/DataImporterTest.java
java -cp out com.superpapermario.DataImporterTest
```

## Pendiente de verificar en el teléfono

- Que el APK arranque con tu zip y que el juego pase del título a la partida.
- Que el formato "Ultrawide sin estirar" se vea bien en tu pantalla (la aplica el runtime, no se pudo probar aquí).
- Rendimiento y GPU (Dawn/Vulkan) en tu teléfono.
- La versión europea (R8PP01) no se ha probado en Android todavía: la traducción y el runtime PAL siguen los pasos del PC,
  pero ninguno de los dos se ha compilado aquí.
- La compilación no se ha probado en CI desde aquí (no hay disco, NDK ni red en el entorno donde se preparó): el
  primer intento de GitHub Actions puede necesitar ajustes. El log dirá exactamente dónde falla.
