# Enemy Infestation (1998) — Edición Español Latino & Lanzador HD

> *"Hay juegos de la infancia que nunca se olvidan: pasillos oscuros, colonos intentando sobrevivir, puertas electrónicas cerrándose justo a tiempo y alienígenas acechando en cada habitación."*

Este proyecto nació del cariño y la nostalgia por volver a jugar **Enemy Infestation** (1998, Clockworks Entertainment / Micro Forte Pty. Ltd., publicado por Ripcord Games) en PCs y monitores modernos, **completamente traducido y doblado al Español Latinoamericano**, con audio remasterizado, escalado HD sin deformar la imagen y un **lanzador gráfico bilingüe (Español / Inglés)**.

Si tú también creciste jugando este clásico de estrategia táctica en tiempo real, **¡eres más que bienvenido a probarlo, reportar mejoras y mandar tu Pull Request!**

> **English summary:** Open-source reverse-engineering toolkit, `BLK0` asset/archive repacker, complete Latin American Spanish localization (text, extended CP1252 bitmap fonts, 97 UI bitmaps, WinRT TTS dubbing + DSP SFX remastering), pre-tuned `cnc-ddraw` HD wrapper, and a native bilingual (`Español` / `English`) Windows launcher (`Configurar y Jugar.exe`) for the 1998 PC classic *Enemy Infestation*. You must supply your own legal original copy of the game to build the playable distribution locally.

---

## ¿Qué mejoramos y qué agregamos?

Todo lo implementado se construyó mediante ingeniería inversa limpia del ejecutable `Ei.exe` (`Watcom C/C++32`) y sus archivos propietarios `.res` (`BLK0`), sin modificar ni dañar la instalación original del juego:

### 1. Ingeniería inversa y reempaquetado completo (`BLK0`)
- **Documentación técnica completa ([`docs/architecture.md`](docs/architecture.md)):** mapeo de `Ei.exe` (61 módulos fuente originales identificados, carga de recursos, protecciones, IA de 16 estados `'MIND'`, sistema de objetivos/condiciones y formato de guardados `save*.res`).
- **Inspector, extractor y reconstrucción binaria ([`tools/blk0.py`](tools/blk0.py)):**
  - Lectura y reempaquetado de contenedores `BLK0` v10 (`auto_idat`, tabla de directorio `DIR ` y recálculo automático de checksums **CRC-16/ARC** `0xA001` mediante slicing-by-8), verificado en los **52 archivos `.res`** originales (**13,116 chunks** sin errores).
  - Códec bidireccional completo para imágenes paletizadas **`cbmp`** (modos Raw `0/1` y compresión transparente **`ZRLE`** `2/3`, **2,442/2,442 chunks** decodificados y re-codificados).
- **Herramientas de análisis y edición ([`tools/export_world.py`](tools/export_world.py), [`tools/save_tool.py`](tools/save_tool.py)):**
  - Exportación estructurada de mapas (`Map*.res`), base de datos (`Stdres.res`), escenarios (`Scen*.res`) y renderizado anotado de habitaciones, techos, puertas y elevadores.
  - Inspector y parcheador seguro CRC-16/ARC para partidas guardadas (`save*.res`).

### 2. Traducción completa al Español Latinoamericano ([`tools/loc_text_exe.py`](tools/loc_text_exe.py), `loc/es/`)
- **Ejecutable [`loc/es/ei_exe.json`](loc/es/ei_exe.json):** `32` cadenas del segmento `DGROUP` traducidas respetando estrictamente el tamaño máximo en bytes `CP1252` sin desplazar código ni punteros.
- **Textos centrales [`loc/es/text_res.json`](loc/es/text_res.json):** `209` entradas localizadas de `Text.res` validando especificadores `printf` (`%s`, `%d`) y espacios estructurales.
- **Base de datos e interfaz [`loc/es/std_structs.json`](loc/es/std_structs.json):** `21` colonos/alienígenas (`patr`), `23` armas/objetos (`wtyp`), `18` efectos (`weft`), `72` objetos del escenario (`pobj`) y `86` tooltips de vista (`view_tooltips`).
- **Mapas y habitaciones [`loc/es/maps.json`](loc/es/maps.json):** los `6` mapas (`12` registros `mapd`) y `159` nombres de salas traducidos.
- **Todas las misiones [`loc/es/scenarios.json`](loc/es/scenarios.json):** los `41` escenarios (`Scen*.res`), `168` títulos de objetivos, `95` nombres de personajes y `619` textos/briefings/diálogos de campaña y multijugador.
- **Documentación clásica:** [`loc/es/Help.txt`](loc/es/Help.txt), [`loc/es/ReadMe.txt`](loc/es/ReadMe.txt) y [`loc/es/Credits.txt`](loc/es/Credits.txt).

### 3. Fuentes bitmap extendidas e interfaz gráfica localizada ([`tools/loc_fonts_ui.py`](tools/loc_fonts_ui.py))
- Las fuentes originales del juego no incluían acentos ni símbolos del español. Se extendieron las **6 fuentes bitmap** de `Stdres.res` (`15002`, `15010`, `15011`, `15012`, `15013`, `15014`) agregando **22 glifos `CP1252`** (`¡ ¿ Á É Í Ñ Ó Ú Ü á é í ñ ó ú ü ª º ° “ ” –`) dentro del límite clásico de ranuras (`<= 128`).
- Se regeneraron **97 gráficos `cbmp` de menús, botones, pestañas y pantallas** integrados con la paleta VGA `pal0 6001` original.

### 4. Doblaje al Español Latino y remasterización de SFX retro ([`tools/loc_audio.py`](tools/loc_audio.py))
- **Doblaje completo en `22050 Hz` PCM 8-bit sin signo:**
  - **709 frases habladas** de personajes dobladas en `Sound.res`.
  - **611 diálogos y narraciones** doblados en los **41 escenarios** (`Scen*.res`).
  - Síntesis con voces en español mexicano de Windows (`Microsoft Raul` y `Microsoft Sabina` vía WinRT TTS) aplicando **12 perfiles de personaje** y filtros DSP (radio táctica, intercomunicador `PA`, comunicaciones y voz robótica) con dithering **TPDF**.
- **Remasterización de efectos de sonido (SFX):**
  - Limpieza DSP aplicada a **265 efectos de sonido** en `Sound.res` (eliminación de sesgo DC, suavizado anti-clipping y cuantización TPDF preservando la longitud exacta en bytes esperada por el motor).

### 5. Compatibilidad HD moderna con `cnc-ddraw` ([`vendor/cnc-ddraw`](vendor/cnc-ddraw), [`tools/build_es.py`](tools/build_es.py))
- Integración del wrapper **cnc-ddraw** (licencia MIT) y colección de **shaders GLSL** (`libretro/glsl-shaders`) preajustados para pantallas actuales (`1080p`, `1440p`, etc.):
  - Modo pantalla completa sin bordes (`fullscreen=true`, `windowed=true`), proporción `4:3` sin estirar (`maintas=true`), renderizado por OpenGL con filtro `Catmull-Rom`, ajuste automático del ratón (`adjmouse=true`), atajo **`Alt+Enter`** y parche `[EI] hook_peekmessage=true`.
  - Accesos directos rápidos para la resolución clásica **`800×600`** y el modo nativo **`1024×768` Alta Vista** (`Ei.exe -r1`, mayor área visible de mapa).

### 6. Lanzador gráfico bilingüe (`Configurar y Jugar.exe`, [`tools/launcher/EiLauncher.cs`](tools/launcher/EiLauncher.cs))
Agregamos una interfaz gráfica nativa para Windows (`.NET Framework 4.0` x86, compilada automáticamente sin depender de Python al jugar) que permite ajustar todo antes de entrar al juego:
- **Selector de idioma completo (`Español (Latinoamérica)` / `English (Original)`):**
  - Cambia al instante el idioma de toda la interfaz del lanzador y sincroniza `cnc-ddraw config.exe` (`spanish` / `english`).
  - Al aplicar cambios, intercambia los **54 archivos dependientes del idioma** (`Ei.exe`, `Text.res`, `Stdres.res`, `Sound.res`, `Map*.res`, `Scen*.res`, `*.txt`) desde `lang/es/` o `lang/en/` **sin tocar tus partidas guardadas (`save*.res`)** ni duplicar música o videos compartidos.
- **Resolución interna (`Ei.exe`):** `800×600` Clásica o `1024×768` Alta Vista (`-r1`).
- **Modo de visualización:** Pantalla completa sin bordes, Pantalla completa exclusiva o Ventana redimensionable (con presets desde `Automático` hasta `2560×1440`).
- **Escalado y calidad visual:** Proporción `4:3`, Escala entera (píxel exacto) o Estirar a pantalla completa; renderizador (`OpenGL`, `Direct3D 9`, `Automático`, `GDI`); **6 filtros GLSL** (`Catmull-Rom`, `Nearest Neighbor`, `Lanczos2 Sharp`, `AMD FSR`, `CRT Lottes`, `xBRZ Freescale`), velocidad del ratón y `VSync`.

---

## Estructura del repositorio

| Ruta | Contenido |
| :--- | :--- |
| [`tools/blk0.py`](tools/blk0.py) | Librería y CLI para inspeccionar, verificar, extraer y reconstruir archivos `BLK0` / `cbmp` |
| [`tools/loc_text_exe.py`](tools/loc_text_exe.py) | Validador de catálogos `CP1252`/`printf` y parcheador de textos/structs/`Ei.exe` |
| [`tools/loc_fonts_ui.py`](tools/loc_fonts_ui.py) | Extensión de fuentes bitmap (`+22` glifos ES) y localización de bitmaps UI |
| [`tools/loc_audio.py`](tools/loc_audio.py) | Doblaje TTS (`es-MX`), filtros DSP de comunicaciones y remasterización SFX PCM8 |
| [`tools/build_es.py`](tools/build_es.py) | Ensamblador completo de `dist/ei_es/` con paquetes `lang/es` + `lang/en` y lanzador `.exe` |
| [`tools/launcher/EiLauncher.cs`](tools/launcher/EiLauncher.cs) | Código fuente C# (WinForms x86) de `Configurar y Jugar.exe` |
| [`tools/export_world.py`](tools/export_world.py) | Exportador JSON/PNG de mapas, base de datos y escenarios |
| [`tools/save_tool.py`](tools/save_tool.py) | Inspector y parcheador seguro para partidas `save*.res` |
| [`loc/es/`](loc/es) | Catálogos JSON de traducción y archivos `.txt` localizados |
| [`vendor/cnc-ddraw/`](vendor/cnc-ddraw) | Wrapper DirectDraw HD (`cnc-ddraw`, MIT) y shaders GLSL (`libretro`) |
| [`docs/architecture.md`](docs/architecture.md) | Notas técnicas de ingeniería inversa de `Ei.exe` y formatos `.res` |
| [`tests/`](tests) | Suite de `28` pruebas automatizadas (`test_blk0.py` y `test_loc_es.py`) |

> Las carpetas `dist/`, `extracted/`, `analysis/` y `loc/es/audio_cache/` están excluidas en [`.gitignore`](.gitignore) para no distribuir binarios ni activos originales con derechos de autor y mantener el repositorio ligero.

---

## Cómo construir tu copia para jugar

### Requisitos
1. **Copia original instalada** de *Enemy Infestation* (por defecto en `C:\Program Files (x86)\Enemy Infestation`, o cualquier otra ruta pasando `--src-dir`).
2. **Windows 10 u 11** con `.NET Framework 4.0` (`csc.exe` incluido en Windows) y el paquete de voz **Español (México)** de Windows (`Microsoft Sabina` / `Microsoft Raul`) si deseas regenerar el caché TTS desde cero.
   - En *Configuración de Windows → Hora e idioma → Voz → Agregar voces*, agrega **Español (México)**.
3. **Python 3.10 o superior** con `Pillow`:
   ```powershell
   pip install -r requirements.txt
   ```

### Pasos de compilación y verificación

```powershell
# 1. (Opcional) Validar todos los catálogos de texto CP1252
python tools/loc_text_exe.py check

# 2. Construir la edición bilingüe HD en dist/ei_es (no modifica la carpeta original)
python tools/build_es.py

# 3. Ejecutar la batería completa de pruebas (28 tests)
python -m unittest discover -s tests -v
```

Si tu instalación original está en otra carpeta:
```powershell
python tools/build_es.py --src-dir "D:\Juegos\Enemy Infestation"
```

Al terminar, ejecuta el lanzador gráfico desde:
```text
dist\ei_es\Configurar y Jugar.exe
```

---

## ¡Invitación a colaborar y mejorar el proyecto!

Este proyecto está abierto para cualquier entusiasta de los juegos clásicos, traductores, diseñadores, programadores o fans de *Enemy Infestation*. Ideas donde puedes ayudar muchísimo:

- **Doblaje con voces humanas reales:** reemplazar total o parcialmente las líneas TTS con grabaciones de actores/colaboradores de la comunidad manteniendo las utilidades DSP de [`tools/loc_audio.py`](tools/loc_audio.py).
- **Revisión de traducción y nuevos idiomas:** pulir diálogos, adaptar modismos o sumar otros paquetes de idioma (`es-ES`, `pt-BR`, etc.) aprovechando la arquitectura modular en `loc/` y el selector de `lang/`.
- **Mejoras al lanzador HD:** selector separado de idioma para textos vs voces, perfiles por misión, soporte más rico de opciones de `Ei.cfg` o controles adicionales.
- **Editor de escenarios y mapas:** ya está documentada la estructura binaria completa de `Map*.res`, `Scen*.res`, `goal` y `lply`; construir un editor visual abriría la puerta a nuevas campañas hechas por la comunidad.
- **Pruebas en múltiples equipos:** validar comportamiento en Windows 10/11, resoluciones ultrawide (`21:9`), Steam Deck / Wine / Proton o tarjetas gráficas variadas.

Si encuentras un error en algún texto, gráfico o misión, o tienes una mejora lista:
1. Haz un **Fork** del repositorio.
2. Crea una rama descriptiva (`git checkout -b feature/mi-mejora`).
3. Ejecuta `python -m unittest discover -s tests -v` para comprobar que todo pase sin regresiones.
4. Abre un **Pull Request** o crea un **Issue** contándonos qué recuerdas de este juegazo y qué te gustaría mejorar.

---

## Créditos y aviso legal

- **Enemy Infestation (1998):** © Clockworks Entertainment / Micro Forte Pty. Ltd. / Ripcord Games. Este repositorio **no distribuye ni aloja archivos originales ni material con copyright** del juego; únicamente provee herramientas de software, catálogos de traducción y automatización para que cada usuario transforme su propia copia legítima.
- **cnc-ddraw:** © FunkyFr3sh ([github.com/FunkyFr3sh/cnc-ddraw](https://github.com/FunkyFr3sh/cnc-ddraw)), distribuido bajo licencia MIT.
- **GLSL Shaders:** © autores de [libretro/glsl-shaders](https://github.com/libretro/glsl-shaders).
