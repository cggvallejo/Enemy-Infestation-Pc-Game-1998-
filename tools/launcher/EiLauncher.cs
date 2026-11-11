using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("Enemy Infestation - Configurador HD / HD Launcher")]
[assembly: AssemblyDescription("Lanzador gráfico bilingüe para configurar idioma, resolución interna y escalado HD (cnc-ddraw).")]
[assembly: AssemblyProduct("Enemy Infestation HD")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

namespace EiLauncherApp
{
    internal sealed class LauncherConfig
    {
        public string Language = "es";            // "es" | "en"
        public string GameResolution = "800x600"; // "800x600" | "1024x768"
        public string DisplayMode = "borderless"; // "borderless" | "fullscreen" | "windowed"
        public string ScaleMode = "aspect";       // "aspect" | "integer" | "stretch"
        public string WindowSize = "0x0";         // "0x0" | "WxH"
        public string Renderer = "opengl";        // "opengl" | "direct3d9" | "auto" | "gdi"
        public string Shader = @"Shaders\interpolation\catmull-rom-bilinear.glsl";
        public bool AdjMouse = true;
        public bool VSync = false;

        public static LauncherConfig CreateRecommendedDefaults()
        {
            return new LauncherConfig();
        }

        public static string NormalizeLanguage(string raw)
        {
            if (string.IsNullOrEmpty(raw))
            {
                return "es";
            }
            string v = raw.Trim().ToLowerInvariant();
            if (v == "en" || v == "english")
            {
                return "en";
            }
            return "es";
        }
    }

    internal static class LanguagePack
    {
        private static readonly string[] RequiredFiles = { "Ei.exe", "Text.res", "Stdres.res", "Sound.res" };

        public static string GetPackRoot(string baseDir)
        {
            return Path.Combine(baseDir, "lang");
        }

        public static string GetPackDir(string baseDir, string lang)
        {
            return Path.Combine(GetPackRoot(baseDir), LauncherConfig.NormalizeLanguage(lang));
        }

        public static bool HasPackRoot(string baseDir)
        {
            return Directory.Exists(GetPackRoot(baseDir));
        }

        public static bool IsPackAvailable(string baseDir, string lang)
        {
            string packDir = GetPackDir(baseDir, lang);
            if (!Directory.Exists(packDir))
            {
                return false;
            }
            foreach (string req in RequiredFiles)
            {
                if (!File.Exists(Path.Combine(packDir, req)))
                {
                    return false;
                }
            }
            return true;
        }

        public static bool FilesEqualBytes(string pathA, string pathB)
        {
            if (!File.Exists(pathA) || !File.Exists(pathB))
            {
                return false;
            }
            var infoA = new FileInfo(pathA);
            var infoB = new FileInfo(pathB);
            if (infoA.Length != infoB.Length)
            {
                return false;
            }
            const int BufSize = 65536;
            byte[] bufA = new byte[BufSize];
            byte[] bufB = new byte[BufSize];
            using (FileStream fsA = File.OpenRead(pathA))
            using (FileStream fsB = File.OpenRead(pathB))
            {
                while (true)
                {
                    int readA = fsA.Read(bufA, 0, BufSize);
                    int readB = fsB.Read(bufB, 0, BufSize);
                    if (readA != readB)
                    {
                        return false;
                    }
                    if (readA == 0)
                    {
                        return true;
                    }
                    for (int i = 0; i < readA; i++)
                    {
                        if (bufA[i] != bufB[i])
                        {
                            return false;
                        }
                    }
                }
            }
        }

        public static bool IsRootSynced(string baseDir, string targetLang, string installedLang)
        {
            string norm = LauncherConfig.NormalizeLanguage(targetLang);
            if (!string.Equals(installedLang, norm, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
            string packDir = GetPackDir(baseDir, norm);
            if (!IsPackAvailable(baseDir, norm))
            {
                return false;
            }
            if (!FilesEqualBytes(Path.Combine(packDir, "Ei.exe"), Path.Combine(baseDir, "Ei.exe"))
                || !FilesEqualBytes(Path.Combine(packDir, "Text.res"), Path.Combine(baseDir, "Text.res")))
            {
                return false;
            }
            foreach (string srcFile in Directory.GetFiles(packDir))
            {
                string dstFile = Path.Combine(baseDir, Path.GetFileName(srcFile));
                if (!File.Exists(dstFile) || new FileInfo(srcFile).Length != new FileInfo(dstFile).Length)
                {
                    return false;
                }
            }
            return true;
        }

        public static bool ApplyPack(string baseDir, string targetLang)
        {
            string norm = LauncherConfig.NormalizeLanguage(targetLang);
            string packDir = GetPackDir(baseDir, norm);
            if (!IsPackAvailable(baseDir, norm))
            {
                throw new DirectoryNotFoundException(
                    string.Format(
                        CultureInfo.InvariantCulture,
                        "No se encontró el paquete de idioma '{0}' en:\n{1}",
                        norm,
                        packDir));
            }

            foreach (string srcFile in Directory.GetFiles(packDir))
            {
                string dstFile = Path.Combine(baseDir, Path.GetFileName(srcFile));
                if (File.Exists(dstFile))
                {
                    FileAttributes attrs = File.GetAttributes(dstFile);
                    if ((attrs & FileAttributes.ReadOnly) != 0)
                    {
                        File.SetAttributes(dstFile, attrs & ~FileAttributes.ReadOnly);
                    }
                }
                File.Copy(srcFile, dstFile, true);
                File.SetAttributes(dstFile, FileAttributes.Normal);
            }
            return true;
        }
    }

    internal static class IniStore
    {
        private const string LauncherIniName = "launcher.ini";
        private const string DdrawIniName = "ddraw.ini";

        public static Dictionary<string, string> ReadIniSection(string path, string targetSection)
        {
            var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (!File.Exists(path))
            {
                return result;
            }

            string current = "";
            string want = targetSection.Trim();
            foreach (string rawLine in File.ReadAllLines(path, Encoding.UTF8))
            {
                string trimmed = rawLine.Trim();
                if (trimmed.StartsWith("[") && trimmed.EndsWith("]"))
                {
                    current = trimmed.Substring(1, trimmed.Length - 2).Trim();
                    continue;
                }
                if (!string.Equals(current, want, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                if (trimmed.Length == 0 || trimmed.StartsWith(";") || trimmed.StartsWith("#"))
                {
                    continue;
                }
                int eq = rawLine.IndexOf('=');
                if (eq <= 0)
                {
                    continue;
                }
                string key = rawLine.Substring(0, eq).Trim();
                string val = rawLine.Substring(eq + 1).Trim();
                result[key] = val;
            }
            return result;
        }

        public static void UpdateIniSection(string path, string targetSection, IDictionary<string, string> updates)
        {
            string[] lines = File.Exists(path)
                ? File.ReadAllLines(path, Encoding.UTF8)
                : new string[0];

            var pending = new Dictionary<string, string>(updates, StringComparer.OrdinalIgnoreCase);
            var outLines = new List<string>(lines.Length + updates.Count + 2);
            string current = "";
            bool foundSection = false;
            bool flushedInSection = false;
            string want = targetSection.Trim();

            for (int i = 0; i < lines.Length; i++)
            {
                string rawLine = lines[i];
                string trimmed = rawLine.Trim();
                if (trimmed.StartsWith("[") && trimmed.EndsWith("]"))
                {
                    if (string.Equals(current, want, StringComparison.OrdinalIgnoreCase) && !flushedInSection)
                    {
                        AppendPending(outLines, pending);
                        flushedInSection = true;
                    }
                    current = trimmed.Substring(1, trimmed.Length - 2).Trim();
                    if (string.Equals(current, want, StringComparison.OrdinalIgnoreCase))
                    {
                        foundSection = true;
                    }
                    outLines.Add(rawLine);
                    continue;
                }

                if (string.Equals(current, want, StringComparison.OrdinalIgnoreCase)
                    && trimmed.Length > 0
                    && !trimmed.StartsWith(";")
                    && !trimmed.StartsWith("#"))
                {
                    int eq = rawLine.IndexOf('=');
                    if (eq > 0)
                    {
                        string rawKey = rawLine.Substring(0, eq).Trim();
                        string newVal;
                        if (pending.TryGetValue(rawKey, out newVal))
                        {
                            outLines.Add(rawKey + "=" + newVal);
                            pending.Remove(rawKey);
                            continue;
                        }
                    }
                }

                outLines.Add(rawLine);
            }

            if (foundSection && !flushedInSection)
            {
                AppendPending(outLines, pending);
            }
            else if (!foundSection)
            {
                if (outLines.Count > 0 && outLines[outLines.Count - 1].Length > 0)
                {
                    outLines.Add("");
                }
                outLines.Add("[" + want + "]");
                AppendPending(outLines, pending);
            }

            string text = string.Join("\r\n", outLines.ToArray()) + "\r\n";
            File.WriteAllText(path, text, new UTF8Encoding(false));
        }

        private static void AppendPending(List<string> outLines, Dictionary<string, string> pending)
        {
            if (pending.Count == 0)
            {
                return;
            }
            int insertAt = outLines.Count;
            while (insertAt > 0 && outLines[insertAt - 1].Trim().Length == 0)
            {
                insertAt--;
            }
            var extra = new List<string>(pending.Count);
            foreach (KeyValuePair<string, string> kv in pending)
            {
                extra.Add(kv.Key + "=" + kv.Value);
            }
            outLines.InsertRange(insertAt, extra);
            pending.Clear();
        }

        public static LauncherConfig Load(string baseDir)
        {
            var cfg = LauncherConfig.CreateRecommendedDefaults();

            Dictionary<string, string> lSec = ReadIniSection(Path.Combine(baseDir, LauncherIniName), "Launcher");
            Dictionary<string, string> ddraw = ReadIniSection(Path.Combine(baseDir, DdrawIniName), "ddraw");

            string langVal;
            if (lSec.TryGetValue("Language", out langVal) && !string.IsNullOrEmpty(langVal))
            {
                cfg.Language = LauncherConfig.NormalizeLanguage(langVal);
            }
            else
            {
                string cfgLang;
                if (ddraw.TryGetValue("configlang", out cfgLang) && string.Equals(cfgLang, "english", StringComparison.OrdinalIgnoreCase))
                {
                    cfg.Language = "en";
                }
                else
                {
                    cfg.Language = "es";
                }
            }

            string gameRes;
            if (lSec.TryGetValue("GameResolution", out gameRes))
            {
                cfg.GameResolution = string.Equals(gameRes, "1024x768", StringComparison.OrdinalIgnoreCase)
                    ? "1024x768"
                    : "800x600";
            }

            if (ddraw.Count == 0)
            {
                return cfg;
            }

            bool fs = ParseBool(ddraw, "fullscreen", true);
            bool win = ParseBool(ddraw, "windowed", true);
            if (fs && win)
            {
                cfg.DisplayMode = "borderless";
            }
            else if (fs)
            {
                cfg.DisplayMode = "fullscreen";
            }
            else
            {
                cfg.DisplayMode = "windowed";
            }

            bool maintas = ParseBool(ddraw, "maintas", true);
            bool boxing = ParseBool(ddraw, "boxing", false);
            if (boxing)
            {
                cfg.ScaleMode = "integer";
            }
            else if (maintas)
            {
                cfg.ScaleMode = "aspect";
            }
            else
            {
                cfg.ScaleMode = "stretch";
            }

            int w = ParseInt(ddraw, "width", 0);
            int h = ParseInt(ddraw, "height", 0);
            cfg.WindowSize = (w > 0 && h > 0)
                ? (w.ToString(CultureInfo.InvariantCulture) + "x" + h.ToString(CultureInfo.InvariantCulture))
                : "0x0";

            string renderer;
            if (ddraw.TryGetValue("renderer", out renderer) && !string.IsNullOrEmpty(renderer))
            {
                cfg.Renderer = renderer.ToLowerInvariant();
            }

            string shader;
            if (ddraw.TryGetValue("shader", out shader) && !string.IsNullOrEmpty(shader))
            {
                cfg.Shader = shader;
            }

            cfg.AdjMouse = ParseBool(ddraw, "adjmouse", true);
            cfg.VSync = ParseBool(ddraw, "vsync", false);
            return cfg;
        }

        public static bool NeedsLanguagePackSync(string baseDir, string targetLang)
        {
            string norm = LauncherConfig.NormalizeLanguage(targetLang);
            if (!LanguagePack.IsPackAvailable(baseDir, norm))
            {
                return false;
            }
            Dictionary<string, string> lSec = ReadIniSection(Path.Combine(baseDir, LauncherIniName), "Launcher");
            string installedLang = "";
            lSec.TryGetValue("InstalledLanguage", out installedLang);
            return !LanguagePack.IsRootSynced(baseDir, norm, installedLang);
        }

        public static void Save(string baseDir, LauncherConfig cfg, bool requirePackIfRequested)
        {
            string ddrawPath = Path.Combine(baseDir, DdrawIniName);
            if (!File.Exists(ddrawPath))
            {
                throw new FileNotFoundException("No se encontró el archivo ddraw.ini en la carpeta del juego.", ddrawPath);
            }

            string normLang = LauncherConfig.NormalizeLanguage(cfg.Language);
            string launcherIniPath = Path.Combine(baseDir, LauncherIniName);
            Dictionary<string, string> prevLauncher = ReadIniSection(launcherIniPath, "Launcher");
            string installedLang = "";
            prevLauncher.TryGetValue("InstalledLanguage", out installedLang);

            bool hasPackRoot = LanguagePack.HasPackRoot(baseDir);
            bool packAvailable = LanguagePack.IsPackAvailable(baseDir, normLang);
            if ((requirePackIfRequested || hasPackRoot) && !packAvailable)
            {
                throw new DirectoryNotFoundException(
                    string.Format(
                        CultureInfo.InvariantCulture,
                        "No se encontró el paquete de idioma '{0}' en {1}.",
                        normLang,
                        LanguagePack.GetPackDir(baseDir, normLang)));
            }

            if (packAvailable && !LanguagePack.IsRootSynced(baseDir, normLang, installedLang))
            {
                LanguagePack.ApplyPack(baseDir, normLang);
                installedLang = normLang;
            }
            else if (packAvailable)
            {
                installedLang = normLang;
            }

            bool fs;
            bool win;
            int outW = 0;
            int outH = 0;

            if (string.Equals(cfg.DisplayMode, "fullscreen", StringComparison.OrdinalIgnoreCase))
            {
                fs = true;
                win = false;
            }
            else if (string.Equals(cfg.DisplayMode, "windowed", StringComparison.OrdinalIgnoreCase))
            {
                fs = false;
                win = true;
                ParseWxH(cfg.WindowSize, out outW, out outH);
            }
            else
            {
                fs = true;
                win = true;
            }

            bool maintas;
            bool boxing;
            if (string.Equals(cfg.ScaleMode, "integer", StringComparison.OrdinalIgnoreCase))
            {
                maintas = true;
                boxing = true;
            }
            else if (string.Equals(cfg.ScaleMode, "stretch", StringComparison.OrdinalIgnoreCase))
            {
                maintas = false;
                boxing = false;
            }
            else
            {
                maintas = true;
                boxing = false;
            }

            var ddrawUpdates = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                { "width", outW.ToString(CultureInfo.InvariantCulture) },
                { "height", outH.ToString(CultureInfo.InvariantCulture) },
                { "fullscreen", fs ? "true" : "false" },
                { "windowed", win ? "true" : "false" },
                { "maintas", maintas ? "true" : "false" },
                { "boxing", boxing ? "true" : "false" },
                { "renderer", string.IsNullOrEmpty(cfg.Renderer) ? "opengl" : cfg.Renderer },
                { "shader", cfg.Shader ?? "" },
                { "adjmouse", cfg.AdjMouse ? "true" : "false" },
                { "vsync", cfg.VSync ? "true" : "false" },
                { "border", "true" },
                { "resizable", "true" },
                { "configlang", normLang == "en" ? "english" : "spanish" },
            };
            UpdateIniSection(ddrawPath, "ddraw", ddrawUpdates);

            var launcherUpdates = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                { "Language", normLang },
                { "GameResolution", string.Equals(cfg.GameResolution, "1024x768", StringComparison.OrdinalIgnoreCase) ? "1024x768" : "800x600" },
            };
            if (!string.IsNullOrEmpty(installedLang))
            {
                launcherUpdates["InstalledLanguage"] = installedLang;
            }
            UpdateIniSection(launcherIniPath, "Launcher", launcherUpdates);
        }

        private static bool ParseBool(Dictionary<string, string> map, string key, bool fallback)
        {
            string val;
            if (!map.TryGetValue(key, out val))
            {
                return fallback;
            }
            if (string.Equals(val, "true", StringComparison.OrdinalIgnoreCase) || val == "1")
            {
                return true;
            }
            if (string.Equals(val, "false", StringComparison.OrdinalIgnoreCase) || val == "0")
            {
                return false;
            }
            return fallback;
        }

        private static int ParseInt(Dictionary<string, string> map, string key, int fallback)
        {
            string val;
            int n;
            if (map.TryGetValue(key, out val) && int.TryParse(val, NumberStyles.Integer, CultureInfo.InvariantCulture, out n))
            {
                return n;
            }
            return fallback;
        }

        public static bool ParseWxH(string spec, out int w, out int h)
        {
            w = 0;
            h = 0;
            if (string.IsNullOrEmpty(spec))
            {
                return false;
            }
            string[] parts = spec.ToLowerInvariant().Split('x');
            if (parts.Length != 2)
            {
                return false;
            }
            int pw;
            int ph;
            if (int.TryParse(parts[0].Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out pw)
                && int.TryParse(parts[1].Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out ph)
                && pw > 0 && ph > 0)
            {
                w = pw;
                h = ph;
                return true;
            }
            return false;
        }
    }

    internal sealed class OptionItem
    {
        public readonly string Value;
        public readonly string Label;

        public OptionItem(string value, string label)
        {
            Value = value;
            Label = label;
        }

        public override string ToString()
        {
            return Label;
        }
    }

    internal sealed class UiStrings
    {
        public string WindowTitle;
        public string HeaderTitle;
        public string MonitorFmt;
        public string CardGame;
        public string RowLang;
        public string RowGameRes;
        public string CardDisplay;
        public string RowDisplayMode;
        public string RowWinSize;
        public string CardScale;
        public string RowScale;
        public string RowRenderer;
        public string RowShader;
        public string ChkAdjMouse;
        public string ChkVSync;
        public string HintWindowed;
        public string HintFullscreen;
        public string HintShaderGl;
        public string HintShaderNonGl;
        public string BtnAdvanced;
        public string BtnReset;
        public string BtnSave;
        public string BtnPlay;
        public string StatusReady;
        public string StatusSaved;
        public string StatusReset;
        public string StatusReloaded;
        public string StatusApplyingLangFmt;
        public string StatusPackMissingFmt;
        public string CustomPrefix;
        public string SaveErrTitle;
        public string SaveErrPrefix;
        public string AdvMissingMsg;
        public string AdvMissingTitle;
        public string AdvOpenErrPrefix;
        public string EiMissingMsg;
        public string EiMissingTitle;
        public string EiStartErrPrefix;
        public OptionItem[] LanguageOptions;
        public OptionItem[] GameResOptions;
        public OptionItem[] DisplayModeOptions;
        public OptionItem[] WindowSizeOptions;
        public OptionItem[] ScaleModeOptions;
        public OptionItem[] RendererOptions;
        public OptionItem[] ShaderOptions;

        public static UiStrings ForLanguage(string lang)
        {
            bool en = string.Equals(LauncherConfig.NormalizeLanguage(lang), "en", StringComparison.OrdinalIgnoreCase);
            if (en)
            {
                return new UiStrings
                {
                    WindowTitle = "Enemy Infestation HD (English) — Configure & Play",
                    HeaderTitle = "ENEMY INFESTATION — HD DISPLAY & LANGUAGE LAUNCHER",
                    MonitorFmt = "Detected display: {0} × {1} px  •  In-game shortcut: Alt+Enter toggles Fullscreen / Windowed",
                    CardGame = "1. Game language & internal resolution (Ei.exe)",
                    RowLang = "Language / Idioma:",
                    RowGameRes = "Internal resolution:",
                    CardDisplay = "2. Display mode & window sizing",
                    RowDisplayMode = "Display mode:",
                    RowWinSize = "Window size:",
                    CardScale = "3. Scaling, aspect ratio & image filter (cnc-ddraw)",
                    RowScale = "Scaling:",
                    RowRenderer = "Renderer:",
                    RowShader = "Visual filter (Shader):",
                    ChkAdjMouse = "Automatically adjust mouse speed for scaled window",
                    ChkVSync = "Vertical sync (VSync — prevents image tearing)",
                    HintWindowed = "Choose a fixed preset size or drag the window corners while playing.",
                    HintFullscreen = "Automatically scales cleanly to fill your current monitor.",
                    HintShaderGl = "The GLSL shader sharpens or smooths pixels on GPU.",
                    HintShaderNonGl = "Note: GLSL shaders require Renderer = OpenGL.",
                    BtnAdvanced = "Advanced (cnc-ddraw)...",
                    BtnReset = "Reset",
                    BtnSave = "Save",
                    BtnPlay = "Save & Play",
                    StatusReady = "Ready. Choose your language and display preferences, then click Save & Play.",
                    StatusSaved = "Settings saved cleanly (Language: {0}).",
                    StatusReset = "Recommended display defaults loaded (click Save or Save & Play).",
                    StatusReloaded = "Settings reloaded after closing cnc-ddraw config.exe.",
                    StatusApplyingLangFmt = "Switching game language to {0}...",
                    StatusPackMissingFmt = "Warning: language pack 'lang\\{0}' was not found in the game folder.",
                    CustomPrefix = "Custom",
                    SaveErrTitle = "Save failed",
                    SaveErrPrefix = "Could not apply settings or switch language files:\n\n",
                    AdvMissingMsg = "'cnc-ddraw config.exe' was not found in the game folder.",
                    AdvMissingTitle = "Missing file",
                    AdvOpenErrPrefix = "Could not launch cnc-ddraw config.exe:\n\n",
                    EiMissingMsg = "Ei.exe was not found in:\n",
                    EiMissingTitle = "Executable not found",
                    EiStartErrPrefix = "Could not start Ei.exe:\n\n",
                    LanguageOptions = new[]
                    {
                        new OptionItem("es", "Español (Latinoamérica) — Doblaje, textos e interfaz"),
                        new OptionItem("en", "English (Original) — Original voices, text & UI"),
                    },
                    GameResOptions = new[]
                    {
                        new OptionItem("800x600", "800 × 600 — Classic (Recommended: original HUD & menu proportions)"),
                        new OptionItem("1024x768", "1024 × 768 — High View (More map visible in-game; menus remain 800×600)"),
                    },
                    DisplayModeOptions = new[]
                    {
                        new OptionItem("borderless", "Borderless fullscreen (Recommended — instant & crisp)"),
                        new OptionItem("fullscreen", "Exclusive fullscreen (Legacy DirectDraw mode)"),
                        new OptionItem("windowed", "Resizable window (Move and drag window borders freely)"),
                    },
                    WindowSizeOptions = new[]
                    {
                        new OptionItem("0x0", "Automatic (Matches game resolution)"),
                        new OptionItem("1280x720", "1280 × 720 (HD 720p)"),
                        new OptionItem("1280x960", "1280 × 960 (4:3 HD)"),
                        new OptionItem("1440x1080", "1440 × 1080 (4:3 Full HD)"),
                        new OptionItem("1600x900", "1600 × 900 (HD+)"),
                        new OptionItem("1600x1200", "1600 × 1200 (4:3 — 2× of 800×600)"),
                        new OptionItem("1920x1080", "1920 × 1080 (Full HD 1080p)"),
                        new OptionItem("2560x1440", "2560 × 1440 (QHD 1440p)"),
                    },
                    ScaleModeOptions = new[]
                    {
                        new OptionItem("aspect", "Keep 4:3 aspect ratio (Recommended — no stretching)"),
                        new OptionItem("integer", "Integer scaling (Exact whole-number pixel multiples)"),
                        new OptionItem("stretch", "Stretch to fill screen (Fills 16:9 width with no bars)"),
                    },
                    RendererOptions = new[]
                    {
                        new OptionItem("opengl", "OpenGL (Recommended — enables GLSL HD shaders)"),
                        new OptionItem("direct3d9", "Direct3D 9 (Hardware fallback)"),
                        new OptionItem("auto", "Automatic"),
                        new OptionItem("gdi", "GDI (Software compatibility mode)"),
                    },
                    ShaderOptions = new[]
                    {
                        new OptionItem(@"Shaders\interpolation\catmull-rom-bilinear.glsl", "Catmull-Rom (Balanced & crisp — Recommended)"),
                        new OptionItem(@"Shaders\nearest-neighbor.glsl", "Nearest Neighbor (Raw retro pixels, no blur)"),
                        new OptionItem(@"Shaders\interpolation\lanczos2-sharp.glsl", "Lanczos2 Sharp (Crisp HD sharpening)"),
                        new OptionItem(@"Shaders\interpolation\fsr.glsl", "AMD FSR (Edge-enhancing HD upscale)"),
                        new OptionItem(@"Shaders\crt\crt-lottes-fast-no-warp-bilinear.glsl", "CRT Lottes (Retro monitor look)"),
                        new OptionItem(@"Shaders\xbrz\xbrz-freescale-multipass.glsl", "xBRZ Freescale (Artistic pixel smoothing)"),
                    },
                };
            }

            return new UiStrings
            {
                WindowTitle = "Enemy Infestation HD (Español) — Configurar y Jugar",
                HeaderTitle = "ENEMY INFESTATION — CONFIGURADOR HD E IDIOMA",
                MonitorFmt = "Monitor detectado: {0} × {1} px  •  Atajo en partida: Alt+Enter alterna Pantalla completa / Ventana",
                CardGame = "1. Idioma y resolución interna del juego (Ei.exe)",
                RowLang = "Idioma / Language:",
                RowGameRes = "Resolución interna:",
                CardDisplay = "2. Modo de visualización y tamaño en tu monitor",
                RowDisplayMode = "Modo de pantalla:",
                RowWinSize = "Tamaño de ventana:",
                CardScale = "3. Escalado, proporción y filtro de imagen (cnc-ddraw)",
                RowScale = "Escalado:",
                RowRenderer = "Renderizador:",
                RowShader = "Filtro visual (Shader):",
                ChkAdjMouse = "Ajustar velocidad del ratón automáticamente al tamaño escalado",
                ChkVSync = "Sincronización vertical (VSync — evita cortes de imagen)",
                HintWindowed = "Puedes elegir un tamaño fijo o arrastrar las esquinas de la ventana jugando.",
                HintFullscreen = "En pantalla completa se adapta automáticamente al tamaño total de tu monitor.",
                HintShaderGl = "El filtro GLSL suaviza o define los píxeles al escalar en GPU.",
                HintShaderNonGl = "Nota: los shaders GLSL requieren Renderizador = OpenGL.",
                BtnAdvanced = "Avanzado (cnc-ddraw)...",
                BtnReset = "Restaurar",
                BtnSave = "Guardar",
                BtnPlay = "Guardar y Jugar",
                StatusReady = "Listo. Elige tu idioma y pantalla, y pulsa Guardar y Jugar.",
                StatusSaved = "Configuración guardada correctamente (Idioma: {0}).",
                StatusReset = "Valores de pantalla recomendados cargados (pulsa Guardar o Guardar y Jugar).",
                StatusReloaded = "Configuración recargada tras cerrar cnc-ddraw config.exe.",
                StatusApplyingLangFmt = "Cambiando archivos del juego a {0}...",
                StatusPackMissingFmt = "Aviso: no se encontró el paquete de idioma 'lang\\{0}' en la carpeta.",
                CustomPrefix = "Personalizado",
                SaveErrTitle = "Error al guardar",
                SaveErrPrefix = "No se pudo guardar la configuración o cambiar los archivos de idioma:\n\n",
                AdvMissingMsg = "No se encontró 'cnc-ddraw config.exe' en la carpeta del juego.",
                AdvMissingTitle = "Archivo faltante",
                AdvOpenErrPrefix = "No se pudo abrir cnc-ddraw config.exe:\n\n",
                EiMissingMsg = "No se encontró Ei.exe en:\n",
                EiMissingTitle = "Ejecutable no encontrado",
                EiStartErrPrefix = "No se pudo iniciar Ei.exe:\n\n",
                LanguageOptions = new[]
                {
                    new OptionItem("es", "Español (Latinoamérica) — Voces, textos e interfaz"),
                    new OptionItem("en", "English (Original) — Voces, textos e interfaz originales"),
                },
                GameResOptions = new[]
                {
                    new OptionItem("800x600", "800 × 600 — Clásica (Recomendada: interfaz y menús al tamaño original)"),
                    new OptionItem("1024x768", "1024 × 768 — Alta Vista (Más mapa visible en partida; menús fijos 800×600)"),
                },
                DisplayModeOptions = new[]
                {
                    new OptionItem("borderless", "Pantalla completa sin bordes (Recomendada — instantánea y nítida)"),
                    new OptionItem("fullscreen", "Pantalla completa exclusiva (Modo DirectDraw tradicional)"),
                    new OptionItem("windowed", "Ventana redimensionable (Puedes mover y estirar el borde)"),
                },
                WindowSizeOptions = new[]
                {
                    new OptionItem("0x0", "Automático (Igual a la resolución del juego)"),
                    new OptionItem("1280x720", "1280 × 720 (HD 720p)"),
                    new OptionItem("1280x960", "1280 × 960 (4:3 HD)"),
                    new OptionItem("1440x1080", "1440 × 1080 (4:3 Full HD)"),
                    new OptionItem("1600x900", "1600 × 900 (HD+)"),
                    new OptionItem("1600x1200", "1600 × 1200 (4:3 — 2× de 800×600)"),
                    new OptionItem("1920x1080", "1920 × 1080 (Full HD 1080p)"),
                    new OptionItem("2560x1440", "2560 × 1440 (QHD 1440p)"),
                },
                ScaleModeOptions = new[]
                {
                    new OptionItem("aspect", "Mantener proporción 4:3 (Recomendada — sin deformar, franjas a los lados)"),
                    new OptionItem("integer", "Escala entera / Píxel exacto (Múltiplos puros sin suavizado fraccionario)"),
                    new OptionItem("stretch", "Estirar a pantalla completa (Llena el ancho 16:9 sin franjas negras)"),
                },
                RendererOptions = new[]
                {
                    new OptionItem("opengl", "OpenGL (Recomendado — activa filtros GLSL HD)"),
                    new OptionItem("direct3d9", "Direct3D 9 (Alternativa de hardware)"),
                    new OptionItem("auto", "Automático"),
                    new OptionItem("gdi", "GDI (Modo compatibilidad por software)"),
                },
                ShaderOptions = new[]
                {
                    new OptionItem(@"Shaders\interpolation\catmull-rom-bilinear.glsl", "Catmull-Rom (Equilibrado y nítido — Recomendado)"),
                    new OptionItem(@"Shaders\nearest-neighbor.glsl", "Nearest Neighbor (Píxel retro puro sin suavizado)"),
                    new OptionItem(@"Shaders\interpolation\lanczos2-sharp.glsl", "Lanczos2 Sharp (Enfoque definido HD)"),
                    new OptionItem(@"Shaders\interpolation\fsr.glsl", "AMD FSR (Realce de bordes HD)"),
                    new OptionItem(@"Shaders\crt\crt-lottes-fast-no-warp-bilinear.glsl", "CRT Lottes (Estilo monitor retro)"),
                    new OptionItem(@"Shaders\xbrz\xbrz-freescale-multipass.glsl", "xBRZ Freescale (Suavizado artístico de píxeles)"),
                },
            };
        }
    }

    internal sealed class LauncherForm : Form
    {
        private static readonly Color BgWindow = Color.FromArgb(20, 25, 32);
        private static readonly Color BgCard = Color.FromArgb(30, 38, 49);
        private static readonly Color BorderCard = Color.FromArgb(52, 66, 84);
        private static readonly Color BgInput = Color.FromArgb(40, 50, 64);
        private static readonly Color TextPrimary = Color.FromArgb(234, 240, 246);
        private static readonly Color TextMuted = Color.FromArgb(164, 178, 196);
        private static readonly Color AccentGreen = Color.FromArgb(46, 178, 98);
        private static readonly Color AccentGreenText = Color.FromArgb(255, 255, 255);
        private static readonly Color SecondaryBtn = Color.FromArgb(48, 60, 76);

        private readonly string _baseDir;
        private readonly ComboBox _cmbLanguage = new ComboBox();
        private readonly ComboBox _cmbGameRes = new ComboBox();
        private readonly ComboBox _cmbDisplayMode = new ComboBox();
        private readonly ComboBox _cmbWindowSize = new ComboBox();
        private readonly ComboBox _cmbScaleMode = new ComboBox();
        private readonly ComboBox _cmbRenderer = new ComboBox();
        private readonly ComboBox _cmbShader = new ComboBox();
        private readonly CheckBox _chkAdjMouse = new CheckBox();
        private readonly CheckBox _chkVSync = new CheckBox();

        private Label _lblTitle;
        private Label _lblMonitor;
        private Label _lblCardGame;
        private Label _lblRowLang;
        private Label _lblRowGameRes;
        private Label _lblCardDisplay;
        private Label _lblRowDisplayMode;
        private Label _lblRowWinSize;
        private Label _lblCardScale;
        private Label _lblRowScale;
        private Label _lblRowRenderer;
        private Label _lblRowShader;
        private readonly Label _lblWindowSizeHint = new Label();
        private readonly Label _lblShaderHint = new Label();
        private readonly Label _lblStatus = new Label();

        private Button _btnAdvanced;
        private Button _btnReset;
        private Button _btnSaveOnly;
        private Button _btnPlay;

        private UiStrings _ui;
        private bool _updatingUi;

        public LauncherForm(string baseDir)
        {
            _baseDir = baseDir;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            BackColor = BgWindow;
            ForeColor = TextPrimary;
            Font = new Font("Segoe UI", 9.5F, FontStyle.Regular);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(656, 664);

            try
            {
                string eiExe = Path.Combine(_baseDir, "Ei.exe");
                if (File.Exists(eiExe))
                {
                    Icon exeIcon = Icon.ExtractAssociatedIcon(eiExe);
                    if (exeIcon != null)
                    {
                        Icon = exeIcon;
                    }
                }
            }
            catch
            {
            }

            LauncherConfig initial = IniStore.Load(_baseDir);
            _ui = UiStrings.ForLanguage(initial.Language);
            BuildLayout();
            LoadConfigIntoUi(initial);
            ApplyUiLanguage(initial.Language, setReadyStatus: true);
        }

        private void BuildLayout()
        {
            var root = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(16, 14, 16, 14),
                ColumnCount = 1,
                RowCount = 6,
                BackColor = BgWindow,
            };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // Header
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // Card 1: Language & Game
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // Card 2: Screen
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // Card 3: Scaling & shader
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); // Status
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100F)); // Bottom buttons

            // Header
            var headerPanel = new Panel { Dock = DockStyle.Fill, AutoSize = true, Margin = new Padding(0, 0, 0, 10) };
            _lblTitle = new Label
            {
                Font = new Font("Segoe UI", 12.5F, FontStyle.Bold),
                ForeColor = Color.FromArgb(118, 234, 158),
                AutoSize = true,
                Location = new Point(0, 0),
            };
            _lblMonitor = new Label
            {
                Font = new Font("Segoe UI", 9F, FontStyle.Regular),
                ForeColor = TextMuted,
                AutoSize = true,
                Location = new Point(0, 26),
            };
            headerPanel.Controls.Add(_lblTitle);
            headerPanel.Controls.Add(_lblMonitor);
            root.Controls.Add(headerPanel, 0, 0);

            // Card 1: Language & internal resolution
            Panel cardGame = CreateCard(128, out _lblCardGame);
            var tbl1 = CreateFormTable(2);
            ConfigureComboStyle(_cmbLanguage);
            ConfigureComboStyle(_cmbGameRes);
            _lblRowLang = AddRow(tbl1, 0, _cmbLanguage);
            _lblRowGameRes = AddRow(tbl1, 1, _cmbGameRes);
            cardGame.Controls.Add(tbl1);
            root.Controls.Add(cardGame, 0, 1);

            // Card 2: Display mode & window size
            Panel cardDisplay = CreateCard(142, out _lblCardDisplay);
            var tbl2 = CreateFormTable(3);
            ConfigureComboStyle(_cmbDisplayMode);
            ConfigureComboStyle(_cmbWindowSize);
            _lblWindowSizeHint.ForeColor = TextMuted;
            _lblWindowSizeHint.Font = new Font("Segoe UI", 8.5F, FontStyle.Italic);
            _lblWindowSizeHint.AutoSize = true;
            _lblWindowSizeHint.Margin = new Padding(4, 3, 0, 0);

            _lblRowDisplayMode = AddRow(tbl2, 0, _cmbDisplayMode);
            _lblRowWinSize = AddRow(tbl2, 1, _cmbWindowSize);
            tbl2.Controls.Add(_lblWindowSizeHint, 1, 2);
            cardDisplay.Controls.Add(tbl2);
            root.Controls.Add(cardDisplay, 0, 2);

            // Card 3: Scaling & Visual Quality
            Panel cardScale = CreateCard(214, out _lblCardScale);
            var tbl3 = CreateFormTable(6);
            ConfigureComboStyle(_cmbScaleMode);
            ConfigureComboStyle(_cmbRenderer);
            ConfigureComboStyle(_cmbShader);

            _lblShaderHint.ForeColor = TextMuted;
            _lblShaderHint.Font = new Font("Segoe UI", 8.5F, FontStyle.Italic);
            _lblShaderHint.AutoSize = true;
            _lblShaderHint.Margin = new Padding(4, 2, 0, 4);

            _chkAdjMouse.ForeColor = TextPrimary;
            _chkAdjMouse.AutoSize = true;
            _chkAdjMouse.Margin = new Padding(4, 4, 0, 2);

            _chkVSync.ForeColor = TextPrimary;
            _chkVSync.AutoSize = true;
            _chkVSync.Margin = new Padding(4, 2, 0, 2);

            _lblRowScale = AddRow(tbl3, 0, _cmbScaleMode);
            _lblRowRenderer = AddRow(tbl3, 1, _cmbRenderer);
            _lblRowShader = AddRow(tbl3, 2, _cmbShader);
            tbl3.Controls.Add(_lblShaderHint, 1, 3);
            tbl3.Controls.Add(_chkAdjMouse, 1, 4);
            tbl3.Controls.Add(_chkVSync, 1, 5);
            cardScale.Controls.Add(tbl3);
            root.Controls.Add(cardScale, 0, 3);

            // Status bar
            _lblStatus.ForeColor = TextMuted;
            _lblStatus.AutoSize = true;
            _lblStatus.Margin = new Padding(2, 4, 2, 8);
            root.Controls.Add(_lblStatus, 0, 4);

            // Bottom buttons
            var btnBar = new TableLayoutPanel
            {
                Dock = DockStyle.Bottom,
                AutoSize = true,
                ColumnCount = 4,
                RowCount = 1,
                BackColor = BgWindow,
                Margin = new Padding(0, 4, 0, 0),
            };
            btnBar.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            btnBar.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            btnBar.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            btnBar.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));

            _btnAdvanced = CreateButton(SecondaryBtn, TextPrimary, 174);
            _btnReset = CreateButton(SecondaryBtn, TextPrimary, 96);
            _btnSaveOnly = CreateButton(SecondaryBtn, TextPrimary, 96);
            _btnPlay = CreateButton(AccentGreen, AccentGreenText, 166);
            _btnPlay.Font = new Font("Segoe UI", 10F, FontStyle.Bold);

            _btnAdvanced.Click += OnOpenAdvanced;
            _btnReset.Click += OnResetDefaults;
            _btnSaveOnly.Click += OnSaveOnly;
            _btnPlay.Click += OnSaveAndPlay;

            btnBar.Controls.Add(_btnAdvanced, 0, 0);
            btnBar.Controls.Add(_btnReset, 1, 0);
            btnBar.Controls.Add(_btnSaveOnly, 2, 0);
            _btnSaveOnly.Anchor = AnchorStyles.Right;
            btnBar.Controls.Add(_btnPlay, 3, 0);
            root.Controls.Add(btnBar, 0, 5);

            AcceptButton = _btnPlay;
            Controls.Add(root);

            _cmbLanguage.SelectedIndexChanged += OnLanguageChanged;
            _cmbDisplayMode.SelectedIndexChanged += delegate
            {
                if (!_updatingUi)
                {
                    UpdateDynamicHints();
                }
            };
            _cmbRenderer.SelectedIndexChanged += delegate
            {
                if (!_updatingUi)
                {
                    UpdateDynamicHints();
                }
            };
        }

        private Panel CreateCard(int height, out Label headerLabel)
        {
            var card = new Panel
            {
                Dock = DockStyle.Top,
                Height = height,
                BackColor = BgCard,
                Padding = new Padding(12, 32, 12, 10),
                Margin = new Padding(0, 0, 0, 10),
            };
            card.Paint += delegate(object s, PaintEventArgs e)
            {
                using (var pen = new Pen(BorderCard, 1))
                {
                    e.Graphics.DrawRectangle(pen, 0, 0, card.Width - 1, card.Height - 1);
                }
            };
            headerLabel = new Label
            {
                Font = new Font("Segoe UI", 9.5F, FontStyle.Bold),
                ForeColor = Color.FromArgb(182, 224, 255),
                AutoSize = true,
                Location = new Point(12, 8),
            };
            card.Controls.Add(headerLabel);
            return card;
        }

        private TableLayoutPanel CreateFormTable(int rows)
        {
            var tbl = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 2,
                RowCount = rows,
                BackColor = BgCard,
            };
            tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 154F));
            tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            for (int i = 0; i < rows; i++)
            {
                tbl.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            }
            return tbl;
        }

        private Label AddRow(TableLayoutPanel tbl, int row, ComboBox combo)
        {
            var lbl = new Label
            {
                ForeColor = TextPrimary,
                AutoSize = true,
                Anchor = AnchorStyles.Left,
                Margin = new Padding(0, 6, 8, 6),
            };
            combo.Dock = DockStyle.Fill;
            combo.Margin = new Padding(4, 3, 0, 3);
            tbl.Controls.Add(lbl, 0, row);
            tbl.Controls.Add(combo, 1, row);
            return lbl;
        }

        private static void ConfigureComboStyle(ComboBox cmb)
        {
            cmb.DropDownStyle = ComboBoxStyle.DropDownList;
            cmb.FlatStyle = FlatStyle.Flat;
            cmb.BackColor = BgInput;
            cmb.ForeColor = TextPrimary;
        }

        private static void PopulateComboPreserving(ComboBox cmb, OptionItem[] items, string desiredValue, string customPrefix)
        {
            cmb.Items.Clear();
            cmb.Items.AddRange(items);
            SelectOrInsertOption(cmb, desiredValue, customPrefix);
        }

        private static Button CreateButton(Color back, Color fore, int width)
        {
            var btn = new Button
            {
                BackColor = back,
                ForeColor = fore,
                FlatStyle = FlatStyle.Flat,
                Height = 34,
                Width = width,
                Cursor = Cursors.Hand,
                Margin = new Padding(0, 0, 8, 0),
            };
            btn.FlatAppearance.BorderColor = BorderCard;
            btn.FlatAppearance.BorderSize = 1;
            return btn;
        }

        private static void SelectOrInsertOption(ComboBox cmb, string value, string customLabelPrefix)
        {
            for (int i = 0; i < cmb.Items.Count; i++)
            {
                var item = cmb.Items[i] as OptionItem;
                if (item != null && string.Equals(item.Value, value, StringComparison.OrdinalIgnoreCase))
                {
                    cmb.SelectedIndex = i;
                    return;
                }
            }
            var custom = new OptionItem(value, customLabelPrefix + " (" + value + ")");
            cmb.Items.Add(custom);
            cmb.SelectedIndex = cmb.Items.Count - 1;
        }

        private static string GetSelectedValue(ComboBox cmb, string fallback)
        {
            var item = cmb.SelectedItem as OptionItem;
            return item != null ? item.Value : fallback;
        }

        private void ApplyUiLanguage(string lang, bool setReadyStatus)
        {
            string norm = LauncherConfig.NormalizeLanguage(lang);
            _ui = UiStrings.ForLanguage(norm);
            _updatingUi = true;
            try
            {
                string curGameRes = GetSelectedValue(_cmbGameRes, "800x600");
                string curMode = GetSelectedValue(_cmbDisplayMode, "borderless");
                string curWin = GetSelectedValue(_cmbWindowSize, "0x0");
                string curScale = GetSelectedValue(_cmbScaleMode, "aspect");
                string curRenderer = GetSelectedValue(_cmbRenderer, "opengl");
                string curShader = GetSelectedValue(_cmbShader, @"Shaders\interpolation\catmull-rom-bilinear.glsl");

                Text = _ui.WindowTitle;
                _lblTitle.Text = _ui.HeaderTitle;
                Rectangle mon = Screen.PrimaryScreen != null ? Screen.PrimaryScreen.Bounds : new Rectangle(0, 0, 1920, 1080);
                _lblMonitor.Text = string.Format(CultureInfo.InvariantCulture, _ui.MonitorFmt, mon.Width, mon.Height);

                _lblCardGame.Text = _ui.CardGame;
                _lblRowLang.Text = _ui.RowLang;
                _lblRowGameRes.Text = _ui.RowGameRes;
                _lblCardDisplay.Text = _ui.CardDisplay;
                _lblRowDisplayMode.Text = _ui.RowDisplayMode;
                _lblRowWinSize.Text = _ui.RowWinSize;
                _lblCardScale.Text = _ui.CardScale;
                _lblRowScale.Text = _ui.RowScale;
                _lblRowRenderer.Text = _ui.RowRenderer;
                _lblRowShader.Text = _ui.RowShader;

                _chkAdjMouse.Text = _ui.ChkAdjMouse;
                _chkVSync.Text = _ui.ChkVSync;
                _btnAdvanced.Text = _ui.BtnAdvanced;
                _btnReset.Text = _ui.BtnReset;
                _btnSaveOnly.Text = _ui.BtnSave;
                _btnPlay.Text = _ui.BtnPlay;

                PopulateComboPreserving(_cmbLanguage, _ui.LanguageOptions, norm, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbGameRes, _ui.GameResOptions, curGameRes, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbDisplayMode, _ui.DisplayModeOptions, curMode, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbWindowSize, _ui.WindowSizeOptions, curWin, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbScaleMode, _ui.ScaleModeOptions, curScale, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbRenderer, _ui.RendererOptions, curRenderer, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbShader, _ui.ShaderOptions, curShader, _ui.CustomPrefix);

                UpdateDynamicHints();

                if (LanguagePack.HasPackRoot(_baseDir) && !LanguagePack.IsPackAvailable(_baseDir, norm))
                {
                    _lblStatus.ForeColor = Color.FromArgb(255, 200, 110);
                    _lblStatus.Text = string.Format(CultureInfo.InvariantCulture, _ui.StatusPackMissingFmt, norm);
                }
                else if (setReadyStatus)
                {
                    _lblStatus.ForeColor = TextMuted;
                    _lblStatus.Text = _ui.StatusReady;
                }
            }
            finally
            {
                _updatingUi = false;
            }
        }

        private void LoadConfigIntoUi(LauncherConfig cfg)
        {
            _updatingUi = true;
            try
            {
                string norm = LauncherConfig.NormalizeLanguage(cfg.Language);
                _ui = UiStrings.ForLanguage(norm);
                PopulateComboPreserving(_cmbLanguage, _ui.LanguageOptions, norm, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbGameRes, _ui.GameResOptions, cfg.GameResolution, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbDisplayMode, _ui.DisplayModeOptions, cfg.DisplayMode, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbWindowSize, _ui.WindowSizeOptions, cfg.WindowSize, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbScaleMode, _ui.ScaleModeOptions, cfg.ScaleMode, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbRenderer, _ui.RendererOptions, cfg.Renderer, _ui.CustomPrefix);
                PopulateComboPreserving(_cmbShader, _ui.ShaderOptions, cfg.Shader, _ui.CustomPrefix);
                _chkAdjMouse.Checked = cfg.AdjMouse;
                _chkVSync.Checked = cfg.VSync;
            }
            finally
            {
                _updatingUi = false;
            }
        }

        private LauncherConfig ReadConfigFromUi()
        {
            return new LauncherConfig
            {
                Language = LauncherConfig.NormalizeLanguage(GetSelectedValue(_cmbLanguage, "es")),
                GameResolution = GetSelectedValue(_cmbGameRes, "800x600"),
                DisplayMode = GetSelectedValue(_cmbDisplayMode, "borderless"),
                WindowSize = GetSelectedValue(_cmbWindowSize, "0x0"),
                ScaleMode = GetSelectedValue(_cmbScaleMode, "aspect"),
                Renderer = GetSelectedValue(_cmbRenderer, "opengl"),
                Shader = GetSelectedValue(_cmbShader, @"Shaders\interpolation\catmull-rom-bilinear.glsl"),
                AdjMouse = _chkAdjMouse.Checked,
                VSync = _chkVSync.Checked,
            };
        }

        private void OnLanguageChanged(object sender, EventArgs e)
        {
            if (_updatingUi)
            {
                return;
            }
            string lang = GetSelectedValue(_cmbLanguage, "es");
            ApplyUiLanguage(lang, setReadyStatus: true);
        }

        private void UpdateDynamicHints()
        {
            bool isWindowed = string.Equals(GetSelectedValue(_cmbDisplayMode, "borderless"), "windowed", StringComparison.OrdinalIgnoreCase);
            _cmbWindowSize.Enabled = isWindowed;
            _lblWindowSizeHint.Text = isWindowed ? _ui.HintWindowed : _ui.HintFullscreen;

            bool isOpenGl = GetSelectedValue(_cmbRenderer, "opengl").StartsWith("opengl", StringComparison.OrdinalIgnoreCase);
            _cmbShader.Enabled = isOpenGl;
            _lblShaderHint.Text = isOpenGl ? _ui.HintShaderGl : _ui.HintShaderNonGl;
        }

        private string GetLanguageDisplayName(string lang)
        {
            return string.Equals(lang, "en", StringComparison.OrdinalIgnoreCase)
                ? "English (Original)"
                : "Español (Latinoamérica)";
        }

        private bool TrySaveCurrentConfig(out LauncherConfig cfg)
        {
            cfg = ReadConfigFromUi();
            bool willSwitch = IniStore.NeedsLanguagePackSync(_baseDir, cfg.Language);
            if (willSwitch)
            {
                Cursor = Cursors.WaitCursor;
                _lblStatus.ForeColor = Color.FromArgb(182, 224, 255);
                _lblStatus.Text = string.Format(
                    CultureInfo.InvariantCulture,
                    _ui.StatusApplyingLangFmt,
                    GetLanguageDisplayName(cfg.Language));
                Application.DoEvents();
            }

            try
            {
                IniStore.Save(_baseDir, cfg, LanguagePack.HasPackRoot(_baseDir));
                return true;
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    this,
                    _ui.SaveErrPrefix + ex.Message,
                    _ui.SaveErrTitle,
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return false;
            }
            finally
            {
                Cursor = Cursors.Default;
            }
        }

        private void OnSaveOnly(object sender, EventArgs e)
        {
            LauncherConfig cfg;
            if (TrySaveCurrentConfig(out cfg))
            {
                _lblStatus.ForeColor = Color.FromArgb(118, 234, 158);
                _lblStatus.Text = string.Format(
                    CultureInfo.InvariantCulture,
                    _ui.StatusSaved,
                    GetLanguageDisplayName(cfg.Language));
            }
        }

        private void OnResetDefaults(object sender, EventArgs e)
        {
            LauncherConfig reset = LauncherConfig.CreateRecommendedDefaults();
            reset.Language = LauncherConfig.NormalizeLanguage(GetSelectedValue(_cmbLanguage, "es"));
            LoadConfigIntoUi(reset);
            ApplyUiLanguage(reset.Language, setReadyStatus: false);
            _lblStatus.ForeColor = Color.FromArgb(182, 224, 255);
            _lblStatus.Text = _ui.StatusReset;
        }

        private void OnOpenAdvanced(object sender, EventArgs e)
        {
            LauncherConfig cfg;
            if (!TrySaveCurrentConfig(out cfg))
            {
                return;
            }

            string cfgExe = Path.Combine(_baseDir, "cnc-ddraw config.exe");
            if (!File.Exists(cfgExe))
            {
                MessageBox.Show(this, _ui.AdvMissingMsg, _ui.AdvMissingTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            try
            {
                var psi = new ProcessStartInfo(cfgExe)
                {
                    WorkingDirectory = _baseDir,
                    UseShellExecute = true,
                };
                using (Process proc = Process.Start(psi))
                {
                    if (proc != null)
                    {
                        proc.WaitForExit();
                    }
                }
                LauncherConfig reloaded = IniStore.Load(_baseDir);
                LoadConfigIntoUi(reloaded);
                ApplyUiLanguage(reloaded.Language, setReadyStatus: false);
                _lblStatus.ForeColor = Color.FromArgb(182, 224, 255);
                _lblStatus.Text = _ui.StatusReloaded;
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, _ui.AdvOpenErrPrefix + ex.Message, _ui.SaveErrTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void OnSaveAndPlay(object sender, EventArgs e)
        {
            LauncherConfig cfg;
            if (!TrySaveCurrentConfig(out cfg))
            {
                return;
            }

            string eiExe = Path.Combine(_baseDir, "Ei.exe");
            if (!File.Exists(eiExe))
            {
                MessageBox.Show(this, _ui.EiMissingMsg + _baseDir, _ui.EiMissingTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            string args = string.Equals(cfg.GameResolution, "1024x768", StringComparison.OrdinalIgnoreCase)
                ? "-r1"
                : "";

            try
            {
                var psi = new ProcessStartInfo(eiExe, args)
                {
                    WorkingDirectory = _baseDir,
                    UseShellExecute = true,
                };
                Process.Start(psi);
                Close();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, _ui.EiStartErrPrefix + ex.Message, _ui.SaveErrTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }

    internal static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        private static int Main(string[] args)
        {
            if (args != null && args.Length > 0 && string.Equals(args[0], "--apply", StringComparison.OrdinalIgnoreCase))
            {
                return RunCliApply(args);
            }

            try
            {
                SetProcessDPIAware();
            }
            catch
            {
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            Application.Run(new LauncherForm(baseDir));
            return 0;
        }

        private static int RunCliApply(string[] args)
        {
            string targetDir = AppDomain.CurrentDomain.BaseDirectory;
            var cfg = LauncherConfig.CreateRecommendedDefaults();
            bool explicitLang = false;

            for (int i = 1; i < args.Length - 1; i++)
            {
                string flag = args[i];
                string val = args[i + 1];
                if (string.Equals(flag, "--dir", StringComparison.OrdinalIgnoreCase))
                {
                    targetDir = val;
                    i++;
                }
                else if (string.Equals(flag, "--lang", StringComparison.OrdinalIgnoreCase))
                {
                    string v = val.ToLowerInvariant();
                    if (v != "es" && v != "en")
                    {
                        return 2;
                    }
                    cfg.Language = v;
                    explicitLang = true;
                    i++;
                }
                else if (string.Equals(flag, "--game-res", StringComparison.OrdinalIgnoreCase))
                {
                    if (!string.Equals(val, "800x600", StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(val, "1024x768", StringComparison.OrdinalIgnoreCase))
                    {
                        return 2;
                    }
                    cfg.GameResolution = val.ToLowerInvariant();
                    i++;
                }
                else if (string.Equals(flag, "--mode", StringComparison.OrdinalIgnoreCase))
                {
                    if (!string.Equals(val, "borderless", StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(val, "fullscreen", StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(val, "windowed", StringComparison.OrdinalIgnoreCase))
                    {
                        return 2;
                    }
                    cfg.DisplayMode = val.ToLowerInvariant();
                    i++;
                }
                else if (string.Equals(flag, "--scale", StringComparison.OrdinalIgnoreCase))
                {
                    if (!string.Equals(val, "aspect", StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(val, "integer", StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(val, "stretch", StringComparison.OrdinalIgnoreCase))
                    {
                        return 2;
                    }
                    cfg.ScaleMode = val.ToLowerInvariant();
                    i++;
                }
                else if (string.Equals(flag, "--win-size", StringComparison.OrdinalIgnoreCase))
                {
                    int pw;
                    int ph;
                    if (!string.Equals(val, "0x0", StringComparison.OrdinalIgnoreCase) && !IniStore.ParseWxH(val, out pw, out ph))
                    {
                        return 2;
                    }
                    cfg.WindowSize = val.ToLowerInvariant();
                    i++;
                }
                else if (string.Equals(flag, "--renderer", StringComparison.OrdinalIgnoreCase))
                {
                    cfg.Renderer = val.ToLowerInvariant();
                    i++;
                }
                else if (string.Equals(flag, "--shader", StringComparison.OrdinalIgnoreCase))
                {
                    cfg.Shader = val;
                    i++;
                }
                else if (string.Equals(flag, "--adjmouse", StringComparison.OrdinalIgnoreCase))
                {
                    cfg.AdjMouse = string.Equals(val, "true", StringComparison.OrdinalIgnoreCase) || val == "1";
                    i++;
                }
                else if (string.Equals(flag, "--vsync", StringComparison.OrdinalIgnoreCase))
                {
                    cfg.VSync = string.Equals(val, "true", StringComparison.OrdinalIgnoreCase) || val == "1";
                    i++;
                }
            }

            try
            {
                IniStore.Save(targetDir, cfg, explicitLang || LanguagePack.HasPackRoot(targetDir));
            }
            catch (Exception ex)
            {
                using (var err = new StreamWriter(Console.OpenStandardError(), new UTF8Encoding(false)))
                {
                    err.WriteLine(ex.Message);
                }
                return 4;
            }

            LauncherConfig roundTrip = IniStore.Load(targetDir);
            if (!string.Equals(roundTrip.Language, cfg.Language, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(roundTrip.GameResolution, cfg.GameResolution, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(roundTrip.DisplayMode, cfg.DisplayMode, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(roundTrip.ScaleMode, cfg.ScaleMode, StringComparison.OrdinalIgnoreCase))
            {
                return 3;
            }
            return 0;
        }
    }
}
