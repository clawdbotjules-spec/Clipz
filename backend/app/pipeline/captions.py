"""CapCut-style animated captions + hook headline, generated as an ASS subtitle file.

Words are grouped into 2-4 word lines. For each word we emit one Dialogue event
covering that word's duration, rendering the whole line with the current word
highlighted — burned in by ffmpeg's `ass` filter in a single pass.

The hook headline is a separate ASS style anchored in the top safe zone
(inside the middle 80% horizontally, below the top 10%, above the bottom 15%)
so TikTok UI never covers it.
"""
from __future__ import annotations

import re
from typing import Any

PLAY_RES_X = 1080
PLAY_RES_Y = 1920

# Safe zone (TikTok UI): keep text below 10% from top, above 15% from bottom,
# inside the middle 80% horizontally.
HOOK_MARGIN_V = int(PLAY_RES_Y * 0.12)        # hook sits just below the top 10%
CAPTION_MARGIN_V = int(PLAY_RES_Y * 0.30)     # captions sit in the lower-middle, above bottom 15%
SIDE_MARGIN = int(PLAY_RES_X * 0.10)

MIN_WORDS_PER_LINE = 2
MAX_WORDS_PER_LINE = 4
MAX_LINE_CHARS = 18  # break early so 4 long words don't overflow


def _hex_to_ass(color: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> ASS '&HAABBGGRR' (ASS is BGR with leading alpha)."""
    color = color.lstrip("#")
    r, g, b = color[0:2], color[2:4], color[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_words(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group whisper words into 2-4 word caption lines, breaking at gaps/punctuation."""
    lines: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    chars = 0
    for i, w in enumerate(words):
        token = w["word"].strip()
        if not token:
            continue
        gap = (w["start"] - words[i - 1]["end"]) if i > 0 else 0.0
        should_break = current and (
            len(current) >= MAX_WORDS_PER_LINE
            or chars + len(token) > MAX_LINE_CHARS and len(current) >= MIN_WORDS_PER_LINE
            or gap > 0.7  # pause in speech = natural line break
        )
        if should_break:
            lines.append(current)
            current, chars = [], 0
        current.append(w)
        chars += len(token) + 1
        if re.search(r"[.!?]$", token) and len(current) >= MIN_WORDS_PER_LINE:
            lines.append(current)
            current, chars = [], 0
    if current:
        lines.append(current)
    return lines


def build_ass(
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    hook: str,
    style: dict[str, Any],
) -> str:
    """Build a complete ASS document. Word times are absolute; we shift to clip-local."""
    font = style.get("caption_font", "Arial Black")
    size = int(style.get("caption_font_size", 72))
    primary = _hex_to_ass(style.get("caption_color", "#FFFFFF"))
    highlight = _hex_to_ass(style.get("caption_highlight_color", "#FFE600"))
    outline = _hex_to_ass(style.get("caption_outline_color", "#000000"))
    hook_size = int(size * 0.82)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_RES_X}
PlayResY: {PLAY_RES_Y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},{primary},{primary},{outline},&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,{SIDE_MARGIN},{SIDE_MARGIN},{CAPTION_MARGIN_V},1
Style: Hook,{font},{hook_size},{primary},{primary},{outline},&H80000000,-1,0,0,0,100,100,0,0,1,7,2,8,{SIDE_MARGIN},{SIDE_MARGIN},{HOOK_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []

    if hook.strip():
        hook_text = _escape(hook.strip().upper())
        events.append(
            f"Dialogue: 1,{_ts(0)},{_ts(clip_end - clip_start)},Hook,,0,0,0,,"
            f"{{\\fad(150,0)}}{hook_text}"
        )

    for line in group_words(words):
        tokens = [_escape(w["word"].strip()) for w in line]
        for idx, w in enumerate(line):
            start = max(w["start"] - clip_start, 0.0)
            # hold until next word starts so the line never flickers
            end = (line[idx + 1]["start"] - clip_start) if idx + 1 < len(line) else (line[-1]["end"] - clip_start)
            end = max(end, start + 0.04)
            parts = []
            for j, tok in enumerate(tokens):
                if j == idx:
                    parts.append(f"{{\\c{highlight}\\fscx108\\fscy108}}{tok}{{\\c{primary}\\fscx100\\fscy100}}")
                else:
                    parts.append(tok)
            events.append(
                f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{' '.join(parts)}"
            )

    return header + "\n".join(events) + "\n"
