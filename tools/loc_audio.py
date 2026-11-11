#!/usr/bin/env python3
"""Audio localization (es-MX WinRT TTS dubbing + retro SFX remastering) for Enemy Infestation."""

from __future__ import annotations

import argparse
import array
import concurrent.futures
import hashlib
import io
import json
import math
import os
import random
import re
import struct
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import blk0  # noqa: E402

TARGET_SR = 22050
DEFAULT_CACHE_DIR = ROOT / "loc" / "es" / "audio_cache"

_U8_TO_F: tuple[float, ...] = tuple((b - 128) / 128.0 for b in range(256))
_TPDF_MASK = 8191
# Deterministic precomputed 8192-sample TPDF dither LUT in LSB units [-0.7, +0.7]
_dither_rng = random.Random(19980930)
_TPDF_LUT: tuple[float, ...] = tuple((_dither_rng.random() - _dither_rng.random()) * 0.7 for _ in range(8192))

VOICE_RAUL = "Microsoft Raul"
VOICE_SABINA = "Microsoft Sabina"

# Character sound-bank profiles keyed by Sound.res band base (1000..12000)
BAND_PROFILES: dict[int, dict[str, Any]] = {
    1000: {"role": "trooper_f", "voice": VOICE_SABINA, "rate": "1.06", "pitch": "+4%", "filter": "radio"},
    2000: {"role": "trooper_m", "voice": VOICE_RAUL, "rate": "1.06", "pitch": "-2%", "filter": "radio"},
    3000: {"role": "physicist", "voice": VOICE_SABINA, "rate": "1.02", "pitch": "-4%", "filter": "comms"},
    4000: {"role": "barman", "voice": VOICE_RAUL, "rate": "0.98", "pitch": "-7%", "filter": "comms"},
    5000: {"role": "technician", "voice": VOICE_SABINA, "rate": "1.05", "pitch": "+7%", "filter": "radio"},
    6000: {"role": "mechanic", "voice": VOICE_RAUL, "rate": "1.00", "pitch": "+4%", "filter": "comms"},
    7000: {"role": "janitor", "voice": VOICE_RAUL, "rate": "0.95", "pitch": "-10%", "filter": "comms"},
    8000: {"role": "cook", "voice": VOICE_RAUL, "rate": "1.03", "pitch": "+8%", "filter": "comms"},
    9000: {"role": "medic", "voice": VOICE_SABINA, "rate": "1.00", "pitch": "0%", "filter": "comms"},
    10000: {"role": "commander", "voice": VOICE_RAUL, "rate": "0.97", "pitch": "-6%", "filter": "radio"},
    11000: {"role": "biologist", "voice": VOICE_SABINA, "rate": "1.01", "pitch": "-7%", "filter": "comms"},
    12000: {"role": "robot", "voice": VOICE_RAUL, "rate": "1.04", "pitch": "+6%", "filter": "robot"},
}

SCEN_PROFILES: dict[str, dict[str, Any]] = {
    "narrator": {"voice": VOICE_SABINA, "rate": "1.02", "pitch": "0%", "filter": "studio"},
    "tutorial": {"voice": VOICE_SABINA, "rate": "1.03", "pitch": "+1%", "filter": "studio"},
    "computer": {"voice": VOICE_SABINA, "rate": "1.04", "pitch": "-3%", "filter": "pa_intercom"},
    "commander": {"voice": VOICE_RAUL, "rate": "0.97", "pitch": "-6%", "filter": "radio"},
    "scen_male": {"voice": VOICE_RAUL, "rate": "1.03", "pitch": "-2%", "filter": "radio"},
    "scen_female": {"voice": VOICE_SABINA, "rate": "1.03", "pitch": "+2%", "filter": "radio"},
    "biologist": {"voice": VOICE_SABINA, "rate": "1.01", "pitch": "-7%", "filter": "comms"},
    "medic": {"voice": VOICE_SABINA, "rate": "1.00", "pitch": "0%", "filter": "comms"},
    "technician": {"voice": VOICE_SABINA, "rate": "1.05", "pitch": "+7%", "filter": "radio"},
    "physicist": {"voice": VOICE_SABINA, "rate": "1.02", "pitch": "-4%", "filter": "comms"},
}

# Bark groups that represent spoken voice lines (grp 100 and 110 are exertion/pain grunts kept as remastered SFX)
SPOKEN_BARK_GROUPS = {
    0, 10, 20, 30, 40, 50, 60, 70, 80, 90,
    130, 140, 150, 160, 170, 180, 200, 210, 230, 240, 250, 260, 270,
}

# Latin American Spanish (es-419 / es-MX) bark lines aligned with Ei.exe callers
HUMAN_BARKS: dict[int, list[str]] = {
    0: [
        "¡Son demasiados! ¡Estamos rodeados!",
        "¡Infestación masiva en el sector!",
        "¡Hay cientos de esas cosas aquí!",
        "¡Alerta máxima, son un enjambre enorme!",
        "¡No vamos a contenerlos si siguen llegando!",
    ],
    10: [
        "Entendido, en marcha.",
        "Recibido, voy para allá.",
        "Claro, moviéndome al punto.",
        "Afirmativo, en camino.",
        "De acuerdo, avanzando.",
    ],
    20: [
        "¡Contacto hostil!",
        "¡Ahí hay uno! ¡Abriendo fuego!",
        "¡Objetivo a la vista!",
        "¡Enemigo detectado, ataco ya!",
        "¡Toma esto, bicho!",
        "¡Acaben con esa cosa!",
    ],
    30: [
        "¡A toda velocidad!",
        "¡Corriendo!",
        "¡Paso veloz!",
    ],
    40: [
        "¡Cubriendo el avance, voy primero!",
        "¡Despejando el sector!",
        "¡Listos, avancemos ahora!",
        "¡Atención equipo, entrando!",
        "¡Voy hacia el objetivo!",
    ],
    50: [
        "¡Estoy muy herido, necesito ayuda!",
        "¡Maldición, me dieron fuerte!",
        "¡Agh, requiero atención médica urgente!",
        "¡Mi estado es crítico!",
        "¡No aguantaré mucho más así!",
    ],
    60: [
        "¡Cuidado, actividad alienígena cerca!",
        "¡Detecté un par de criaturas!",
        "¡Atentos, hay bichos adelante!",
        "¡Contacto menor en el área!",
        "¡Vi movimiento por ahí!",
    ],
    70: [
        "¡Grupo de aliens acercándose!",
        "¡Son varios! ¡Preparen las armas!",
        "¡Varios hostiles en el corredor!",
        "¡Ahí vienen más de ellos!",
        "¡Amenaza múltiple al frente!",
        "¡Nos están cerrando el paso!",
    ],
    80: [
        "¡Es la Reina! ¡Cuidado todos!",
        "¡Madre mía, la Reina alienígena está aquí!",
        "¡Contacto con la Reina, máxima precaución!",
        "¡Por el cielo, es enorme! ¡La Reina!",
        "¡Alerta total, la Reina a la vista!",
        "¡Retirada o fuego concentrado, es la Reina!",
    ],
    90: [
        "¿Sí?",
        "¿Órdenes?",
        "A la orden.",
        "Aquí estoy.",
        "¿Qué necesita?",
        "Escucho.",
        "Listo para actuar.",
    ],
    130: [
        "¡Agh... no puedo más!",
        "¡Todo... se oscurece...!",
    ],
    140: [
        "Te tengo, aguanta un poco más.",
        "Vamos, te sacaré de aquí.",
        "No te preocupes, ya te cargo.",
        "Resiste, te llevo a salvo.",
        "Sujétate, vamos a la bahía médica.",
    ],
    150: [
        "¡Directo en el blanco! ¡Eso sí les duele!",
        "¡Excelente, esta arma los destroza!",
    ],
    160: [
        "¡No les hace casi nada!",
        "¡Necesitamos un arma más potente!",
    ],
    170: [
        "¡Cuidado, eso los está haciendo crecer!",
        "¡Alto el fuego, se vuelven más grandes!",
    ],
    180: [
        "¡Rayos, se están multiplicando!",
        "¡No disparen con eso, se dividen en dos!",
    ],
    200: [
        "¡Bien, eso los hace retroceder!",
        "¡Perfecto, los estamos repeliendo!",
    ],
    210: [
        "¡Ja, mira cómo se encogen!",
        "¡Buen disparo, se están reduciendo!",
    ],
    230: [
        "¡Algo no anda bien aquí!",
        "¡Cuidado con ese sector!",
        "¡Mantengan la guardia alta!",
    ],
    240: [
        "Quédate quieto, te voy a curar.",
        "Aplicando primeros auxilios ahora.",
        "Tranquilo, esto detendrá la hemorragia.",
        "Signos vitales estabilizándose.",
        "Listo, ya deberías sentirte mejor.",
    ],
    250: [
        "¡Uno menos!",
        "¡Objetivo eliminado!",
        "¡Abatido! ¿Quién sigue?",
        "¡Bicho liquidado!",
        "¡Fuera de combate!",
        "¡Despejado, cayó!",
    ],
    260: [
        "Uf, ya estoy mucho mejor.",
        "Listo para volver al servicio.",
        "Recuperado y en pie otra vez.",
        "Gracias, ya puedo continuar.",
    ],
    270: [
        "Equipamiento listo.",
        "Esto me será muy útil.",
    ],
}

# Feminine adjustments for Sabina-voiced bands (1000, 3000, 5000, 9000, 11000)
FEM_OVERRIDES: dict[int, dict[int, str]] = {
    50: {0: "¡Estoy muy herida, necesito ayuda!"},
    90: {6: "Lista para actuar."},
    260: {2: "Recuperada y en pie otra vez."},
}

# Personality tweaks for Commander (10000) and Robot (12000)
BAND_OVERRIDES: dict[int, dict[int, dict[int, str]]] = {
    10000: {
        90: {0: "Comandante al habla.", 1: "Informe la situación.", 4: "¿Cuál es el plan?"},
        10: {0: "Movilizando posición.", 1: "Voy al frente."},
        50: {0: "¡Me alcanzaron! ¡Médico!"},
    },
    12000: {
        0: {0: "Alerta: densidad hostil extrema."},
        10: {0: "Orden confirmada. En tránsito.", 1: "Desplazamiento programado."},
        20: {0: "Amenaza detectada. Neutralizando."},
        30: {0: "Modo de desplazamiento rápido activado."},
        40: {0: "Iniciando maniobra de aproximación."},
        50: {0: "Advertencia: integridad estructural crítica."},
        60: {0: "Escáner detecta organismo hostil."},
        70: {0: "Múltiples entidades biológicas detectadas."},
        80: {0: "Alerta máxima: espécimen Reina localizado."},
        90: {0: "Unidad de servicio operativa.", 1: "Esperando instrucciones.", 2: "Sistemas en línea."},
        130: {0: "Fallo crítico de sistemas... apagando."},
        140: {0: "Asistencia activada. Trasladando tripulante."},
        150: {0: "Impacto óptimo confirmado."},
        160: {0: "Eficacia del armamento insuficiente."},
        170: {0: "Anomalía: incremento de masa hostil."},
        180: {0: "Alerta: replicación celular acelerada."},
        200: {0: "Efecto repulsivo confirmado."},
        210: {0: "Reducción de volumen hostil exitosa."},
        250: {0: "Entidad hostil neutralizada."},
    },
}


def bark_text_for_chunk(band: int, grp: int, idx: int) -> str:
    if band in BAND_OVERRIDES and grp in BAND_OVERRIDES[band] and idx in BAND_OVERRIDES[band][grp]:
        return BAND_OVERRIDES[band][grp][idx]
    pool = HUMAN_BARKS.get(grp)
    if not pool:
        return "Recibido."
    text = pool[idx % len(pool)]
    profile = BAND_PROFILES[band]
    if profile["voice"] == VOICE_SABINA and grp in FEM_OVERRIDES and idx in FEM_OVERRIDES[grp]:
        text = FEM_OVERRIDES[grp][idx]
    return text


def clean_tts_text(text: str) -> str:
    """Normalize control characters and acronyms so WinRT es-MX reads naturally."""
    t = text.replace("\x02", " ").replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\bCOMUN\.", "Comunicaciones", t)
    t = re.sub(r"\bDra\.", "Doctora", t)
    t = re.sub(r"\bDr\.", "Doctor", t)
    t = re.sub(r"\bMD\b", "doctora", t)
    t = re.sub(r"\blab\.", "laboratorio", t, flags=re.IGNORECASE)
    t = re.sub(r"\n+", ". ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t or "Recibido."


def _pcm8_to_floats(raw: bytes) -> list[float]:
    u8f = _U8_TO_F
    return [u8f[b] for b in raw]


def _floats_to_pcm8(samples: list[float], *, seed: int = 0, avoid_extremes: bool = True) -> bytes:
    """Quantize [-1.0, 1.0] float audio to unsigned 8-bit PCM with TPDF dither."""
    n = len(samples)
    out = bytearray(n)
    lo, hi = (1, 254) if avoid_extremes else (0, 255)
    lut = _TPDF_LUT
    mask = _TPDF_MASK
    s = seed & mask
    tanh = math.tanh
    for i in range(n):
        x = samples[i]
        if x > 0.85:
            x = 0.85 + 0.145 * tanh((x - 0.85) / 0.145)
        elif x < -0.85:
            x = -0.85 + 0.145 * tanh((x + 0.85) / 0.145)
        q = int(x * 128.0 + 128.5 + lut[(i + s) & mask])
        if q < lo:
            q = lo
        elif q > hi:
            q = hi
        out[i] = q
    return bytes(out)


def _hpf_coeff(cutoff_hz: float, sr: int = TARGET_SR) -> float:
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / sr
    return rc / (rc + dt)


def _lpf_coeff(cutoff_hz: float, sr: int = TARGET_SR) -> float:
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / sr
    return dt / (rc + dt)


def _one_pole_hpf(samples: list[float], cutoff_hz: float, sr: int = TARGET_SR) -> list[float]:
    alpha = _hpf_coeff(cutoff_hz, sr)
    out = [0.0] * len(samples)
    prev_y = 0.0
    prev_x = 0.0
    for i, x in enumerate(samples):
        y = alpha * (prev_y + x - prev_x)
        out[i] = y
        prev_y = y
        prev_x = x
    return out


def _one_pole_lpf(samples: list[float], cutoff_hz: float, sr: int = TARGET_SR) -> list[float]:
    alpha = _lpf_coeff(cutoff_hz, sr)
    out = [0.0] * len(samples)
    y = 0.0
    for i, x in enumerate(samples):
        y = y + alpha * (x - y)
        out[i] = y
    return out


def remaster_sfx_pcm8(raw: bytes, *, chunk_id: int = 0) -> bytes:
    """Remaster a 22050Hz 8-bit SFX clip while preserving its exact byte length."""
    n = len(raw)
    if n < 64:
        return raw
    lo_b = min(raw)
    hi_b = max(raw)
    peak_raw = max(128 - lo_b, hi_b - 128) / 128.0
    if peak_raw < 0.02:
        return raw

    # C-speed DC mean calculation + single fused HPF + gentle 2.2kHz clarity shelf pass
    dc = (sum(raw) / n - 128.0) / 128.0
    u8f = _U8_TO_F
    a_hp = _hpf_coeff(45.0, TARGET_SR)
    a_lp = _lpf_coeff(2200.0, TARGET_SR)
    py = 0.0
    px = 0.0
    lp = 0.0
    xs = [0.0] * n
    new_peak = 0.0
    for i, b in enumerate(raw):
        v = u8f[b] - dc
        y = a_hp * (py + v - px)
        py = y
        px = v
        lp += a_lp * (y - lp)
        s = y + 0.22 * (y - lp)
        xs[i] = s
        as_ = s if s >= 0.0 else -s
        if as_ > new_peak:
            new_peak = as_

    edge = min(220, n // 6)
    head_rms = math.sqrt(sum(v * v for v in xs[:edge]) / max(1, edge))
    tail_rms = math.sqrt(sum(v * v for v in xs[-edge:]) / max(1, edge))
    is_loop = head_rms > 0.05 and tail_rms > 0.05

    # Soft tail noise-gate on transient SFX to suppress 8-bit fade-out hiss
    if not is_loop and peak_raw > 0.18:
        win = 440  # ~20ms
        for off in range(0, n, win):
            end = min(n, off + win)
            blk = xs[off:end]
            rms = math.sqrt(sum(v * v for v in blk) / len(blk))
            if rms < 0.014:
                gain = max(0.30, rms / 0.014)
                for j in range(off, end):
                    xs[j] *= gain

    # Balanced gain staging: bring weak SFX up (capped at +6 dB) and leave hot hits clean
    if new_peak > 1e-6:
        scale = 1.0
        if new_peak < 0.86:
            scale = min(2.0, 0.88 / new_peak)
        elif new_peak > 0.96:
            scale = 0.94 / new_peak
        if scale != 1.0:
            xs = [v * scale for v in xs]

    fi = 32 if is_loop else min(55, n // 8)
    fo = 32 if is_loop else min(88, n // 6)
    inv_fi = 1.0 / fi if fi else 0.0
    inv_fo = 1.0 / fo if fo else 0.0
    for i in range(fi):
        xs[i] *= i * inv_fi
    for i in range(fo):
        xs[n - 1 - i] *= i * inv_fo

    return _floats_to_pcm8(xs, seed=0x5EED0000 ^ chunk_id, avoid_extremes=True)


def _resample_cubic(xs: list[float], src_sr: int, dst_sr: int = TARGET_SR) -> list[float]:
    n = len(xs)
    if src_sr == dst_sr or n < 4:
        return list(xs)
    out_len = max(1, int(round(n * dst_sr / src_sr)))
    ratio = src_sr / dst_sr
    out = [0.0] * out_len
    n1 = n - 1
    limit = n - 2
    for i in range(out_len):
        pos = i * ratio
        idx = int(pos)
        t = pos - idx
        if 1 <= idx < limit:
            p0 = xs[idx - 1]
            p1 = xs[idx]
            p2 = xs[idx + 1]
            p3 = xs[idx + 2]
        else:
            p0 = xs[0 if idx < 1 else (n1 if idx - 1 > n1 else idx - 1)]
            p1 = xs[idx if idx <= n1 else n1]
            p2 = xs[idx + 1 if idx + 1 <= n1 else n1]
            p3 = xs[idx + 2 if idx + 2 <= n1 else n1]
        a = -0.5 * p0 + 1.5 * p1 - 1.5 * p2 + 0.5 * p3
        b = p0 - 2.5 * p1 + 2.0 * p2 - 0.5 * p3
        c = -0.5 * p0 + 0.5 * p2
        out[i] = ((a * t + b) * t + c) * t + p1
    return out


def _trim_silence(xs: list[float], sr: int, thresh: float = 0.012) -> list[float]:
    n = len(xs)
    start = 0
    while start < n and -thresh < xs[start] < thresh:
        start += 1
    end = n - 1
    while end > start and -thresh < xs[end] < thresh:
        end -= 1
    if start >= end:
        return xs
    lead = max(0, start - int(sr * 0.018))
    tail = min(n, end + int(sr * 0.040))
    return xs[lead:tail]


def tts_wav_to_pcm8(wav_bytes: bytes, *, filter_mode: str, seed: int = 0) -> bytes:
    """Decode WinRT 16kHz mono PCM WAV, resample to 22050Hz, apply voice DSP, return 8-bit PCM."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if sw != 2:
        raise ValueError(f"Expected 16-bit WAV, got width={sw}")
    arr = array.array("h")
    arr.frombytes(frames)
    inv32k = 1.0 / 32768.0
    if nch > 1:
        xs = [arr[i] * inv32k for i in range(0, len(arr), nch)]
    else:
        xs = [v * inv32k for v in arr]

    xs = _trim_silence(xs, sr)
    xs = _resample_cubic(xs, sr, TARGET_SR)
    n = len(xs)

    # Fused single-pass voice EQ + optional PA/robot modulation
    if filter_mode == "studio":
        hp_c, lp_c, mid_c, mid_k = 75.0, 9500.0, 2600.0, 0.16
    elif filter_mode == "radio":
        hp_c, lp_c, mid_c, mid_k = 210.0, 4400.0, 1500.0, 0.30
    elif filter_mode == "comms":
        hp_c, lp_c, mid_c, mid_k = 140.0, 5200.0, 1900.0, 0.22
    elif filter_mode == "pa_intercom":
        hp_c, lp_c, mid_c, mid_k = 240.0, 4100.0, 1800.0, 0.18
    else:  # robot
        hp_c, lp_c, mid_c, mid_k = 230.0, 4800.0, 1800.0, 0.20

    a_hp = _hpf_coeff(hp_c, TARGET_SR)
    a_lp = _lpf_coeff(lp_c, TARGET_SR)
    a_mid = _lpf_coeff(mid_c, TARGET_SR)
    py = px = lp_y = mid_y = 0.0
    for i in range(n):
        x = xs[i]
        y = a_hp * (py + x - px)
        py = y
        px = x
        lp_y += a_lp * (y - lp_y)
        mid_y += a_mid * (lp_y - mid_y)
        xs[i] = lp_y + mid_k * (lp_y - mid_y)

    if filter_mode == "pa_intercom":
        d1, d2 = 352, 748
        pa = list(xs)
        for i in range(d1, n):
            v = xs[i] + 0.20 * xs[i - d1]
            if i >= d2:
                v += 0.09 * xs[i - d2]
            pa[i] = v
        xs = pa
    elif filter_mode == "robot":
        delay = 78
        comb = [0.0] * n
        two_pi_f = 2.0 * math.pi * 185.0 / TARGET_SR
        sin = math.sin
        for i in range(n):
            c = xs[i] + (0.42 * comb[i - delay] if i >= delay else 0.0)
            comb[i] = 0.72 * c + 0.28 * c * sin(two_pi_f * i)
        xs = comb

    # Gentle RMS leveling + soft ceiling at 0.88 (single pass for sq_sum & peak)
    sq_sum = 0.0
    peak = 0.0
    for v in xs:
        sq_sum += v * v
        av = v if v >= 0.0 else -v
        if av > peak:
            peak = av
    rms = math.sqrt(sq_sum / max(1, n))
    if rms > 1e-4 and peak > 1e-6:
        target_rms = 0.24 if filter_mode != "studio" else 0.22
        gain = min(target_rms / rms, 0.90 / peak) * 1.15
        tanh = math.tanh
        for i in range(n):
            xs[i] = tanh(xs[i] * gain) * 0.90

    fi = min(44, n // 8)
    fo = min(88, n // 6)
    inv_fi = 1.0 / fi if fi else 0.0
    inv_fo = 1.0 / fo if fo else 0.0
    for i in range(fi):
        xs[i] *= i * inv_fi
    for i in range(fo):
        xs[n - 1 - i] *= i * inv_fo

    return _floats_to_pcm8(xs, seed=seed, avoid_extremes=True)


def tts_cache_key(voice: str, rate: str, pitch: str, text: str) -> str:
    payload = f"{voice}\n{rate}\n{pitch}\n{text}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _tts_wav_path(cache_dir: Path, voice: str, rate: str, pitch: str, text: str) -> Path:
    return cache_dir / "tts" / f"{tts_cache_key(voice, rate, pitch, text)}.wav"


def _tts_pcm8_path(cache_dir: Path, key: str, filter_mode: str) -> Path:
    return cache_dir / "pcm8" / f"{key}_{filter_mode}.pcm8"


def _sfx_pcm8_path(cache_dir: Path, raw_sha1: str, seed_id: int) -> Path:
    return cache_dir / "sfx8" / f"{raw_sha1}_{seed_id}.pcm8"


def _worker_tts_pcm8(job: tuple[str, str, str, int]) -> None:
    wav_str, pcm8_str, filter_mode, seed = job
    pcm = tts_wav_to_pcm8(Path(wav_str).read_bytes(), filter_mode=filter_mode, seed=seed)
    Path(pcm8_str).write_bytes(pcm)


def _worker_sfx_pcm8(job: tuple[bytes, str, int]) -> None:
    raw, pcm8_str, seed_id = job
    Path(pcm8_str).write_bytes(remaster_sfx_pcm8(raw, chunk_id=seed_id))


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def synthesize_missing_wavs(items: list[dict[str, str]], cache_dir: Path = DEFAULT_CACHE_DIR) -> int:
    """Batch-synthesize any uncached WinRT es-MX WAVs in a single PowerShell session."""
    tts_dir = cache_dir / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    todo: dict[str, dict[str, str]] = {}
    for it in items:
        key = tts_cache_key(it["voice"], it["rate"], it["pitch"], it["text"])
        out_p = tts_dir / f"{key}.wav"
        if not out_p.exists() or out_p.stat().st_size < 128:
            todo[key] = {**it, "out": str(out_p)}

    if not todo:
        return 0

    manifest_path = cache_dir / "_synth_manifest.json"
    ps1_path = cache_dir / "_synth_batch.ps1"
    manifest_path.write_text(json.dumps(list(todo.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    ps1_code = r"""param([string]$ManifestPath)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($WinRtTask, $ResultType) {
    $netTask = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

$voices = @{}
foreach ($v in [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices) {
    $voices[$v.DisplayName] = $v
}
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$items = Get-Content -Raw -Encoding UTF8 $ManifestPath | ConvertFrom-Json
$total = $items.Count
$idx = 0
foreach ($it in $items) {
    $idx++
    $synth.Voice = $voices[$it.voice]
    $ssml = $it.ssml
    $stream = Await ($synth.SynthesizeSsmlToStreamAsync($ssml)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $size = [uint32]$stream.Size
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    $loaded = Await ($reader.LoadAsync($size)) ([uint32])
    $bytes = New-Object byte[] $loaded
    $reader.ReadBytes($bytes)
    [System.IO.File]::WriteAllBytes($it.out, $bytes)
    $reader.Dispose()
    $stream.Dispose()
    if (($idx % 100) -eq 0 -or $idx -eq $total) {
        Write-Host "TTS progress: $idx / $total"
    }
}
"""
    ps1_path.write_text(ps1_code, encoding="utf-8")

    payload = []
    for entry in todo.values():
        cleaned = _xml_escape(clean_tts_text(entry["text"]))
        ssml = (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='es-MX'>"
            f"<prosody rate='{entry['rate']}' pitch='{entry['pitch']}'>{cleaned}</prosody></speak>"
        )
        payload.append({"voice": entry["voice"], "ssml": ssml, "out": entry["out"]})
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1_path), str(manifest_path)],
        check=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"WinRT TTS batch exited with {proc.returncode}")
    return len(todo)


def _quick_f0(body: bytes) -> float:
    """Fast pitch estimate on a 8-bit 22050Hz source voice clip to aid male/female casting."""
    if len(body) < 2000:
        return 0.0
    n = min(len(body), TARGET_SR * 3)
    f0s: list[float] = []
    for s0 in range(500, max(501, n - 500), 3307):
        seg = [x - 128 for x in body[s0 : s0 + 450]]
        if sum(v * v for v in seg) / 450 < 25.0:
            continue
        e0 = sum(v * v for v in seg[:180])
        best_r, best_lag = 0.0, 0
        for lag in range(62, 265, 4):
            c = sum(seg[j] * seg[j + lag] for j in range(180))
            e1 = sum(seg[j + lag] * seg[j + lag] for j in range(180))
            r = c / math.sqrt(e0 * e1 + 1e-9)
            if r > best_r:
                best_r, best_lag = r, lag
        if best_r > 0.60 and best_lag:
            f0s.append(TARGET_SR / best_lag)
    if not f0s:
        return 0.0
    f0s.sort()
    return f0s[len(f0s) // 2]


def choose_scen_profile(filename: str, cid: int, en_text: str, orig_body: bytes) -> dict[str, Any]:
    """Select scenario narrator, PA computer, or male/female cast profile for a Scen snd8 clip."""
    if cid == 501:
        return SCEN_PROFILES["narrator"]
    if filename == "Scen00.res":
        return SCEN_PROFILES["tutorial"]

    low = en_text.lower()
    # System / base PA announcements
    if any(
        k in low
        for k in (
            "is dead",
            "has died",
            "alien presence terminated",
            "safety interlocks",
            "flooding initiated",
            "all personnel evacuated",
            "radiation vented",
            "fire has started",
            "fire eliminated",
            "fire in ",
            "lifeforce critical",
            "too many deaths",
            "game over",
            "oxygen supplies",
            "reinforcements have arrived",
            "the fire is out",
        )
    ):
        return SCEN_PROFILES["computer"]

    if "commander" in low and ("scorched" in low or "sir" in low):
        # Spoken TO Commander -> likely Bonnie / crew
        pass
    if any(k in low for k in ("listen up", "i order you", "disobeyed my orders", "commander")):
        f0 = _quick_f0(orig_body)
        if f0 == 0.0 or f0 < 165.0:
            return SCEN_PROFILES["commander"]

    f0 = _quick_f0(orig_body)
    if 0.0 < f0 < 162.0:
        return SCEN_PROFILES["scen_male"]
    if f0 >= 162.0:
        return SCEN_PROFILES["scen_female"]
    if any(k in low for k in ("sir", "maam", "ma'am")):
        return SCEN_PROFILES["scen_male"]
    return SCEN_PROFILES["scen_female"]


def plan_sound_res(snd_arc: blk0.Blk0Archive) -> list[dict[str, Any]]:
    """Plan localization actions (dub vs remaster vs passthrough) for every chunk in Sound.res."""
    plan: list[dict[str, Any]] = []
    for idx, c in enumerate(snd_arc.chunks):
        if c.tag != "snd8":
            plan.append({"idx": idx, "action": "keep"})
            continue
        cid = c.chunk_id
        if 1000 <= cid < 13000:
            band = (cid // 1000) * 1000
            grp = ((cid % 1000) // 10) * 10
            var_i = cid % 10
            if grp in SPOKEN_BARK_GROUPS:
                prof = BAND_PROFILES[band]
                plan.append(
                    {
                        "idx": idx,
                        "action": "dub",
                        "cid": cid,
                        "band": band,
                        "grp": grp,
                        "text": bark_text_for_chunk(band, grp, var_i),
                        "profile": prof,
                        "sub_id": 2,
                    }
                )
                continue
        plan.append({"idx": idx, "action": "remaster", "cid": cid, "sub_id": c.sub_id})
    return plan


def plan_scen_audio(
    filename: str,
    scen_arc: blk0.Blk0Archive,
    tables: dict[str, Any],
    f0_cache: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Plan dubbing/remastering for all snd8 chunks inside a Scen*.res archive."""
    plan: list[dict[str, Any]] = []
    _, briefing_es = tables["scen"].get(filename, ("", ""))
    for idx, c in enumerate(scen_arc.chunks):
        if c.tag != "snd8" or len(c.body) <= 100:
            continue
        cid = c.chunk_id
        if cid == 501:
            if not briefing_es:
                continue
            plan.append(
                {
                    "idx": idx,
                    "cid": cid,
                    "text": briefing_es,
                    "en": "",
                    "profile": SCEN_PROFILES["narrator"],
                    "sub_id": c.sub_id,
                }
            )
        elif (filename, cid) in tables["scen_text"]:
            text_es = tables["scen_text"][(filename, cid)]
            key = f"{filename}:{cid}"
            if f0_cache is not None and key in f0_cache:
                # Re-use cached F0 classification without scanning PCM again
                f0 = f0_cache[key]
                if filename == "Scen00.res":
                    prof = SCEN_PROFILES["tutorial"]
                elif 0.0 < f0 < 162.0:
                    prof = SCEN_PROFILES["scen_male"]
                else:
                    prof = SCEN_PROFILES["scen_female"]
            else:
                prof = choose_scen_profile(filename, cid, text_es, c.body)
            plan.append(
                {
                    "idx": idx,
                    "cid": cid,
                    "text": text_es,
                    "profile": prof,
                    "sub_id": c.sub_id,
                }
            )
    return plan


def prepare_all_audio_cache(
    game_dir: str | Path,
    tables: dict[str, Any],
    scen_en_map: dict[tuple[str, int], str],
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> dict[str, Any]:
    """Ensure all WinRT TTS source WAVs and speaker F0 metadata are cached locally."""
    gdir = Path(game_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f0_path = cache_dir / "scen_f0.json"
    f0_cache: dict[str, float] = json.loads(f0_path.read_text("utf-8")) if f0_path.exists() else {}

    tts_requests: list[dict[str, str]] = []
    snd_arc = blk0.Blk0Archive(gdir / "Sound.res")
    snd_plan = plan_sound_res(snd_arc)
    for item in snd_plan:
        if item["action"] == "dub":
            p = item["profile"]
            tts_requests.append(
                {"voice": p["voice"], "rate": p["rate"], "pitch": p["pitch"], "text": item["text"]}
            )

    scen_plans: dict[str, list[dict[str, Any]]] = {}
    f0_dirty = False
    for p in sorted(gdir.glob("Scen*.res")):
        # Fast DIR scan of snd8 chunks avoids re-hashing unrelated sprites when planning cache
        data = p.read_bytes()
        dir_off = struct.unpack_from("<I", data, 6)[0]
        dcnt = struct.unpack_from("<H", data, dir_off + 10)[0]
        entries: list[dict[str, Any]] = []
        for i in range(dcnt):
            tag_b, cid, coff = struct.unpack_from("<4sHI", data, dir_off + 16 + i * 10)
            if tag_b != b"snd8":
                continue
            psize = struct.unpack_from("<I", data, coff + 4)[0]
            if psize <= 104:
                continue
            sub_id = struct.unpack_from("<H", data, coff + 16)[0]
            body = data[coff + 20 : coff + 16 + psize]
            if cid == 501:
                _, brief_es = tables["scen"].get(p.name, ("", ""))
                if not brief_es:
                    continue
                prof = SCEN_PROFILES["narrator"]
                text_es = brief_es
            else:
                text_es = tables["scen_text"].get((p.name, cid))
                if not text_es:
                    continue
                fkey = f"{p.name}:{cid}"
                if fkey not in f0_cache:
                    f0_cache[fkey] = round(_quick_f0(body), 1)
                    f0_dirty = True
                prof = _profile_from_f0_and_en(p.name, cid, scen_en_map.get((p.name, cid), ""), f0_cache[fkey])
            entries.append({"idx": i, "cid": cid, "text": text_es, "profile": prof, "sub_id": sub_id})
            tts_requests.append(
                {"voice": prof["voice"], "rate": prof["rate"], "pitch": prof["pitch"], "text": text_es}
            )
        if entries:
            scen_plans[p.name] = entries

    if f0_dirty:
        f0_path.write_text(json.dumps(f0_cache, indent=2, sort_keys=True), encoding="utf-8")

    synthesized = synthesize_missing_wavs(tts_requests, cache_dir)

    # Precompute processed 22050Hz 8-bit PCM blobs in parallel across CPU cores
    pcm8_dir = cache_dir / "pcm8"
    sfx8_dir = cache_dir / "sfx8"
    pcm8_dir.mkdir(parents=True, exist_ok=True)
    sfx8_dir.mkdir(parents=True, exist_ok=True)

    tts_jobs: dict[tuple[str, str], tuple[str, str, str, int]] = {}
    for item in snd_plan:
        if item["action"] == "dub":
            p = item["profile"]
            key = tts_cache_key(p["voice"], p["rate"], p["pitch"], item["text"])
            out_p = _tts_pcm8_path(cache_dir, key, p["filter"])
            if not out_p.exists() or out_p.stat().st_size == 0:
                wav_p = cache_dir / "tts" / f"{key}.wav"
                tts_jobs[(key, p["filter"])] = (str(wav_p), str(out_p), p["filter"], int(item["cid"]))

    for entries in scen_plans.values():
        for entry in entries:
            p = entry["profile"]
            key = tts_cache_key(p["voice"], p["rate"], p["pitch"], entry["text"])
            out_p = _tts_pcm8_path(cache_dir, key, p["filter"])
            if not out_p.exists() or out_p.stat().st_size == 0:
                wav_p = cache_dir / "tts" / f"{key}.wav"
                tts_jobs[(key, p["filter"])] = (str(wav_p), str(out_p), p["filter"], int(entry["cid"]))

    sfx_jobs: list[tuple[bytes, str, int]] = []
    for item in snd_plan:
        if item["action"] == "remaster":
            idx = item["idx"]
            c = snd_arc.chunks[idx]
            seed_id = c.chunk_id + idx * 17
            raw_sha1 = hashlib.sha1(c.body).hexdigest()
            out_p = _sfx_pcm8_path(cache_dir, raw_sha1, seed_id)
            if not out_p.exists() or out_p.stat().st_size != len(c.body):
                sfx_jobs.append((c.body, str(out_p), seed_id))

    if tts_jobs or sfx_jobs:
        workers = min(8, os.cpu_count() or 4)
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            if sfx_jobs:
                list(pool.map(_worker_sfx_pcm8, sfx_jobs))
            if tts_jobs:
                list(pool.map(_worker_tts_pcm8, list(tts_jobs.values())))

    return {
        "sound_plan": snd_plan,
        "scen_plans": scen_plans,
        "f0_cache": f0_cache,
        "synthesized_now": synthesized,
        "pcm8_baked_now": len(tts_jobs),
        "sfx_remastered_now": len(sfx_jobs),
        "total_requests": len(tts_requests),
    }


def _profile_from_f0_and_en(filename: str, cid: int, en_text: str, f0: float) -> dict[str, Any]:
    if cid == 501:
        return SCEN_PROFILES["narrator"]
    if filename == "Scen00.res":
        return SCEN_PROFILES["tutorial"]
    low = en_text.lower()
    if any(
        k in low
        for k in (
            "is dead",
            "has died",
            "alien presence terminated",
            "safety interlocks",
            "flooding initiated",
            "all personnel evacuated",
            "radiation vented",
            "fire has started",
            "fire eliminated",
            "fire in ",
            "lifeforce critical",
            "too many deaths",
            "game over",
            "oxygen supplies",
            "reinforcements have arrived",
            "the fire is out",
        )
    ):
        return SCEN_PROFILES["computer"]
    if any(k in low for k in ("listen up", "i order you", "disobeyed my orders")) and (f0 == 0.0 or f0 < 165.0):
        return SCEN_PROFILES["commander"]
    if 0.0 < f0 < 162.0:
        return SCEN_PROFILES["scen_male"]
    if f0 >= 162.0:
        return SCEN_PROFILES["scen_female"]
    if any(k in low for k in ("sir", "maam", "ma'am")):
        return SCEN_PROFILES["scen_male"]
    return SCEN_PROFILES["scen_female"]


def apply_sound_res_audio(
    chunks: list[blk0.Blk0Chunk],
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> tuple[list[blk0.ChunkSpec], dict[str, int]]:
    """Build localized & remastered Sound.res chunk list."""
    out: list[blk0.ChunkSpec] = []
    counts = {"dub": 0, "remaster": 0, "keep": 0}
    for idx, c in enumerate(chunks):
        if c.tag != "snd8":
            out.append(c)
            counts["keep"] += 1
            continue
        cid = c.chunk_id
        if 1000 <= cid < 13000:
            band = (cid // 1000) * 1000
            grp = ((cid % 1000) // 10) * 10
            if grp in SPOKEN_BARK_GROUPS:
                prof = BAND_PROFILES[band]
                text = bark_text_for_chunk(band, grp, cid % 10)
                key = tts_cache_key(prof["voice"], prof["rate"], prof["pitch"], text)
                pcm_p = _tts_pcm8_path(cache_dir, key, prof["filter"])
                if pcm_p.exists() and pcm_p.stat().st_size > 0:
                    body = pcm_p.read_bytes()
                else:
                    wav_p = _tts_wav_path(cache_dir, prof["voice"], prof["rate"], prof["pitch"], text)
                    body = tts_wav_to_pcm8(wav_p.read_bytes(), filter_mode=prof["filter"], seed=cid)
                fc = max(1, (len(body) + 24575) // 24576)
                out.append(("snd8", cid, fc, c.reserved, 2, body))
                counts["dub"] += 1
                continue
        seed_id = cid + idx * 17
        raw_sha1 = hashlib.sha1(c.body).hexdigest()
        sfx_p = _sfx_pcm8_path(cache_dir, raw_sha1, seed_id)
        if sfx_p.exists() and sfx_p.stat().st_size == len(c.body):
            body = sfx_p.read_bytes()
        else:
            body = remaster_sfx_pcm8(c.body, chunk_id=seed_id)
        out.append(("snd8", cid, c.flags_or_count, c.reserved, c.sub_id, body))
        counts["remaster"] += 1
    return out, counts


def apply_scen_audio(
    filename: str,
    specs: list[blk0.ChunkSpec],
    tables: dict[str, Any],
    scen_en_map: dict[tuple[str, int], str],
    f0_cache: dict[str, float],
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> tuple[list[blk0.ChunkSpec], int]:
    """Replace >100B Scen*.res snd8 chunks with dubbed es-MX speech while keeping silent stubs."""
    out: list[blk0.ChunkSpec] = []
    dubbed = 0
    _, brief_es = tables["scen"].get(filename, ("", ""))

    for item in specs:
        if isinstance(item, blk0.Blk0Chunk):
            tag, cid, fc, res, sub_id, body = (
                item.tag,
                item.chunk_id,
                item.flags_or_count,
                item.reserved,
                item.sub_id,
                item.body,
            )
        else:
            tag, cid, fc, res, sub_id, body = item

        if tag != "snd8" or len(body) <= 100:
            out.append(item)
            continue

        if cid == 501:
            text_es = brief_es
            prof = SCEN_PROFILES["narrator"]
        else:
            text_es = tables["scen_text"].get((filename, cid))
            f0 = f0_cache.get(f"{filename}:{cid}", 0.0)
            prof = _profile_from_f0_and_en(filename, cid, scen_en_map.get((filename, cid), ""), f0)

        if not text_es:
            out.append(item)
            continue

        key = tts_cache_key(prof["voice"], prof["rate"], prof["pitch"], text_es)
        pcm_p = _tts_pcm8_path(cache_dir, key, prof["filter"])
        if pcm_p.exists() and pcm_p.stat().st_size > 0:
            new_body = pcm_p.read_bytes()
        else:
            wav_p = _tts_wav_path(cache_dir, prof["voice"], prof["rate"], prof["pitch"], text_es)
            new_body = tts_wav_to_pcm8(wav_p.read_bytes(), filter_mode=prof["filter"], seed=cid)
        new_fc = (len(new_body) + 24575) // 24576 + 1
        out.append(("snd8", cid, new_fc, res, sub_id, new_body))
        dubbed += 1
    return out, dubbed


def main(argv: list[str] | None = None) -> int:
    import loc_text_exe

    ap = argparse.ArgumentParser(description="Prepare and cache es-MX audio dubs and verify SFX remastering.")
    ap.add_argument("cmd", choices=["prepare", "stats"])
    ap.add_argument("--game-dir", type=Path, default=Path(r"C:\Program Files (x86)\Enemy Infestation"))
    ap.add_argument("--loc-dir", type=Path, default=ROOT / "loc" / "es")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = ap.parse_args(argv)

    cats = loc_text_exe.load_catalogs(args.loc_dir)
    tables = loc_text_exe.build_lookup_tables(cats)
    scen_en_map = {(r["file"], r["id"]): r["en"] for r in cats["scenarios"]["scen_texts"]}

    if args.cmd == "stats":
        snd = blk0.Blk0Archive(args.game_dir / "Sound.res")
        plan = plan_sound_res(snd)
        dub = sum(1 for x in plan if x["action"] == "dub")
        rem = sum(1 for x in plan if x["action"] == "remaster")
        keep = sum(1 for x in plan if x["action"] == "keep")
        print(f"Sound.res plan: total={len(plan)}, dub={dub}, remaster_sfx={rem}, keep={keep}")
        return 0

    res = prepare_all_audio_cache(args.game_dir, tables, scen_en_map, args.cache_dir)
    print(
        f"Audio cache ready: total_tts_refs={res['total_requests']}, "
        f"newly_synthesized={res['synthesized_now']}, "
        f"scen_files_with_audio={len(res['scen_plans'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
