#!/usr/bin/env python3
"""Offline speech-to-text: Whisper (ONNX) + Silero VAD. No API, no network at run time.

    transcribe.py AUDIO [--lang he] [--model small] [--out DIR]

Writes <name>.txt and <name>.srt into --out and prints the transcript to stdout.
Models are cached in ~/.cache/asr and fetched from GitHub releases on first use.
"""
import argparse
import os
import re
import subprocess
import sys
import tarfile
import time

import numpy as np

CACHE = os.environ.get("ASR_CACHE", os.path.expanduser("~/.cache/asr"))
RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
SR = 16000
MAX_WINDOW = 25.0  # Whisper's receptive field is 30s; leave headroom
BIDI = re.compile("[‎‏‪-‮⁦-⁩]")

# measured on 4 CPU cores, ratio of audio-seconds transcribed per wall-second
SPEED = {"tiny": 12.0, "base": 6.5, "small": 2.0, "medium": 0.64, "large-v3": 0.35}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fetch(url, dest):
    subprocess.run(["curl", "-fL", "--retry", "3", "-o", dest, url], check=True)


def ensure_model(name):
    d = os.path.join(CACHE, f"sherpa-onnx-whisper-{name}")
    if not os.path.isdir(d):
        os.makedirs(CACHE, exist_ok=True)
        tar = os.path.join(CACHE, f"{name}.tar.bz2")
        log(f"downloading whisper-{name} (one time, ~30s)...")
        fetch(f"{RELEASE}/sherpa-onnx-whisper-{name}.tar.bz2", tar)
        with tarfile.open(tar) as t:
            t.extractall(CACHE)
        os.remove(tar)
    return d


def ensure_vad():
    p = os.path.join(CACHE, "silero_vad.onnx")
    if not os.path.exists(p):
        os.makedirs(CACHE, exist_ok=True)
        fetch(f"{RELEASE}/silero_vad.onnx", p)
    return p


def model_paths(d, name):
    enc = os.path.join(d, f"{name}-encoder.int8.onnx")
    dec = os.path.join(d, f"{name}-decoder.int8.onnx")
    if not os.path.exists(enc):  # a few archives ship fp32 only
        enc = os.path.join(d, f"{name}-encoder.onnx")
        dec = os.path.join(d, f"{name}-decoder.onnx")
    return enc, dec, os.path.join(d, f"{name}-tokens.txt")


def decode_audio(path):
    """Any container or codec -> mono float32 @16kHz, via PyAV's bundled ffmpeg."""
    import av

    with av.open(path) as container:
        streams = [s for s in container.streams if s.type == "audio"]
        if not streams:
            sys.exit(f"no audio track in {path}")
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SR)
        out = []
        for frame in container.decode(streams[0]):
            for f in resampler.resample(frame):
                out.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            out.append(f.to_ndarray().reshape(-1))
    if not out:
        sys.exit("decoded 0 samples")
    return np.concatenate(out).astype(np.float32)


def speech_spans(samples, vad_path):
    """Silero VAD -> [(start_sample, end_sample)]; fixed windows if it finds nothing."""
    import sherpa_onnx

    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = vad_path
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.4
    cfg.silero_vad.min_speech_duration = 0.2
    cfg.silero_vad.max_speech_duration = MAX_WINDOW
    cfg.sample_rate = SR
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)

    spans, win = [], 512
    def drain():
        while not vad.empty():
            s = vad.front
            spans.append((s.start, s.start + len(s.samples)))
            vad.pop()

    for i in range(0, len(samples), win):
        vad.accept_waveform(samples[i : i + win])
        drain()
    vad.flush()
    drain()

    if not spans:
        step = int(MAX_WINDOW * SR)
        spans = [(i, min(i + step, len(samples))) for i in range(0, len(samples), step)]
    return spans


def merge_spans(spans, limit=MAX_WINDOW):
    """Glue neighbouring speech spans into windows of up to `limit` seconds.

    Whisper is far more accurate with a few seconds of surrounding context than
    on isolated one-word fragments, so we hand it the widest window that still
    fits its 30s receptive field. Slicing stays contiguous, silence included,
    which keeps word boundaries intact.
    """
    cap = limit * SR
    out = []
    for a, b in spans:
        if out and b - out[-1][0] <= cap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def srt_time(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--lang", default="he", help="he, en, ar, ru, ... or 'auto' (default: he)")
    ap.add_argument("--model", default="small", choices=list(SPEED))
    ap.add_argument("--out", default=None, help="output directory (default: next to the input)")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    args = ap.parse_args()

    if not os.path.exists(args.audio):
        sys.exit(f"no such file: {args.audio}")

    import sherpa_onnx

    d = ensure_model(args.model)
    vad_path = ensure_vad()
    enc, dec, tok = model_paths(d, args.model)

    samples = decode_audio(args.audio)
    dur = len(samples) / SR
    log(f"audio: {dur / 60:.1f} min")

    windows = merge_spans(speech_spans(samples, vad_path))
    speech = sum(b - a for a, b in windows) / SR
    log(f"speech: {speech / 60:.1f} min in {len(windows)} windows")
    log(f"model: whisper-{args.model}, lang={args.lang}, eta ~{speech / SPEED[args.model] / 60:.0f} min")

    rec = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=enc, decoder=dec, tokens=tok,
        language="" if args.lang == "auto" else args.lang,
        task="transcribe", num_threads=args.threads, decoding_method="greedy_search",
    )

    started, lines = time.time(), []
    for i, (a, b) in enumerate(windows, 1):
        st = rec.create_stream()
        st.accept_waveform(SR, samples[a:b])
        rec.decode_stream(st)
        text = BIDI.sub("", st.result.text).strip()
        if text:
            lines.append((a / SR, b / SR, text))
        done = sum(y - x for x, y in windows[:i]) / SR
        left = (speech - done) / max(done / (time.time() - started), 1e-6)
        log(f"  {i}/{len(windows)} [{a / SR / 60:5.1f}m] ~{left / 60:.0f} min left | {text[:60]}")

    stem = os.path.splitext(os.path.basename(args.audio))[0]
    outdir = args.out or os.path.dirname(os.path.abspath(args.audio))
    os.makedirs(outdir, exist_ok=True)
    txt_path = os.path.join(outdir, stem + ".txt")
    srt_path = os.path.join(outdir, stem + ".srt")

    plain = "\n".join(t for _, _, t in lines)
    with open(txt_path, "w") as f:
        f.write(plain + "\n")
    with open(srt_path, "w") as f:
        for i, (a, b, t) in enumerate(lines, 1):
            f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n")

    log(f"\ndone in {(time.time() - started) / 60:.1f} min\n{txt_path}\n{srt_path}\n")
    print(plain)


if __name__ == "__main__":
    main()
