---
name: transcribe
description: Transcribe an audio or video file to text, fully offline (Whisper + Silero VAD via sherpa-onnx). Hebrew by default, any Whisper language. Use whenever the user hands over a voice message, recording, meeting audio, voice memo, podcast, or video and wants it turned into text, summarized, searched, or quoted — including "תמלל", "מה נאמר בהקלטה", "תהפוך לטקסט", "transcribe this", "what does this recording say". Handles mp3, m4a, wav, ogg, opus, aac, flac, mp4, mov, and anything else ffmpeg reads.
---

# Transcribing audio

Claude cannot listen to audio directly. This skill runs Whisper locally in the
session container instead, so nothing leaves the machine and no API key is needed.

## Run it

```bash
bash .claude/skills/transcribe/setup.sh                      # once per session, ~20s
python3 .claude/skills/transcribe/transcribe.py AUDIO_FILE   # defaults: --lang he --model small
```

Progress streams to stderr with a live ETA. The transcript goes to stdout, and
`<name>.txt` plus `<name>.srt` land next to the input (override with `--out DIR`).

Long files: start it with `run_in_background: true` and check back, rather than
blocking on a foreground call that may outlast the tool timeout.

## Choosing a model

`--model` trades speed for accuracy. Measured on this container's 4 cores, as
minutes of wall time per 10 minutes of *speech* (silence is skipped by the VAD):

| model | 10 min of speech | when to use |
|---|---|---|
| `base` | ~1.5 min | English only, or just locating a passage |
| `small` | ~5 min | **default** — solid for clear Hebrew speech |
| `medium` | ~16 min | noisy audio, accents, several speakers |
| `large-v3` | ~28 min | best Hebrew accuracy; worth it under ~10 min of audio |

First use of a model downloads it from GitHub releases into `~/.cache/asr`
(small 639MB, large-v3 1.1GB, ~30s at this container's bandwidth). It is cached
for the rest of the session but the container is ephemeral, so a new session
re-downloads.

Rule of thumb: reach for `large-v3` when the recording is short or the wording
has to be exact (quotes, legal, medical, numbers). Use `small` for the rest.
Say which model you used, so the user can ask for a more accurate pass.

## Other languages

`--lang en`, `--lang ar`, `--lang ru`, any Whisper code — or `--lang auto` to
detect. The language must be set correctly: forcing the wrong one makes Whisper
"translate" phonetically into that script and produce confident nonsense.

## After transcribing

Hand back what was actually asked for. Usually that is the content — a summary,
the decisions, the answer to a question about the recording — not a wall of raw
transcript. Offer the `.txt`/`.srt` files rather than pasting long transcripts
into chat.

Whisper output has no speaker labels and light punctuation. It also hallucinates
fluent text over silence or noise, so a stretch that reads oddly smoothly next to
a long gap is worth flagging rather than reporting as speech.
