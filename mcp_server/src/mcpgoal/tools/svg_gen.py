"""SVG generation tool — hybrid SDXL prompt + technical SVG instructions.

Accepts a normal SDXL-style description, wraps it in a technical SVG template,
maps SDXL style keywords to concrete SVG techniques, validates the output XML,
checks complexity (paths/gradients/filters/elements) and refines up to 2 times
until the result is rich enough. Saves to Allowed_root/private_svg/.
"""
import json
import os
import re
import time

_STYLE_PRESETS = {
    "detailed": "highly detailed, intricate details, masterpiece, best quality",
    "flat": "flat design, vibrant colors, clean geometric shapes, modern, soft gradients",
    "realistic": "realistic proportions, cinematic lighting, soft shadows, depth of field, textured",
    "minimal": "minimalist, clean lines, negative space, limited color palette, elegant",
    "logo": "minimal line art logo, black strokes, transparent background, clean vector style",
}

# SDXL style keyword -> concrete SVG technique instruction
_KEYWORD_RULES = [
    (r"line art|monochrome|transparent background|stroke|logo",
     "Use fill='none' shapes with a single stroke color and varied stroke-width. "
     "No background rectangle at all (transparent). Clean smooth bezier curves. "
     "No gradients, no color palette."),

    (r"highly detailed|intricate|masterpiece|best quality|detailed",
     "Use at least 15 path elements with bezier curves (C, S, Q commands). "
     "Add small scene details: textures, patterns, secondary objects, highlights."),
    (r"cinematic lighting|lighting|dramatic",
     "Add radial gradients for light sources, semi-transparent light overlays, "
     "and reflective highlights on surfaces."),
    (r"soft shadows|shadows|shadow",
     "Use feDropShadow filters and/or semi-transparent dark shapes for soft shadows "
     "under every object."),
    (r"vibrant colors|colorful|rich colors",
     "Use a saturated 6-8 color palette with smooth gradient transitions between hues."),
    (r"depth of field|bokeh|blur",
     "Blur the background layer with feGaussianBlur and keep the subject sharp."),
    (r"minimal|minimalist|clean lines|negative space",
     "Use a limited 2-4 color palette, generous negative space, crisp simple paths "
     "with clean curves — but still well constructed with gradients for depth."),
    (r"flat design|geometric|modern",
     "Use clean geometric compositions with flat shapes layered to create depth, "
     "plus subtle gradients for highlights."),
]

_FEW_SHOT_A = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="800" height="600">
  <defs>
    <linearGradient id="skyA" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3a4a7a"/><stop offset="45%" stop-color="#e8a064"/>
      <stop offset="100%" stop-color="#f6d8a8"/>
    </linearGradient>
    <linearGradient id="ridgeA" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#6d5a8a"/><stop offset="100%" stop-color="#3f3558"/>
    </linearGradient>
    <linearGradient id="rockA" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#7a8a99"/><stop offset="100%" stop-color="#48525e"/>
    </linearGradient>
    <filter id="blurA"><feGaussianBlur stdDeviation="10"/></filter>
    <filter id="shadowA"><feDropShadow dx="3" dy="8" stdDeviation="6" flood-opacity="0.4"/></filter>
  </defs>

  <rect width="800" height="600" fill="url(#skyA)"/>
  <circle cx="620" cy="150" r="70" fill="#ffe9b0" filter="url(#blurA)" opacity="0.8"/>
  <circle cx="620" cy="150" r="34" fill="#fff3cf"/>

  <g fill="url(#ridgeA)" opacity="0.65">
    <path d="M0 430 C30 402 55 415 90 380 C120 352 155 358 190 330 C225 302 260 315 300 296 C340 278 380 290 420 268 C450 252 480 262 520 240 C555 220 585 232 620 214 C655 196 690 210 725 190 C755 174 780 180 800 166 L800 430 Z"/>
    <path d="M0 470 C45 430 90 452 130 415 C165 385 200 400 235 372 C275 340 315 352 350 322 C385 292 425 305 460 280 C495 255 530 268 565 246 C600 224 635 240 670 220 C705 200 745 215 800 190 L800 470 Z"/>
  </g>
  <g fill="url(#rockA)" filter="url(#shadowA)">
    <path d="M0 520 C25 478 45 486 70 452 C95 418 120 430 150 404 C180 378 210 392 240 368 C265 348 285 355 310 340 C340 322 370 338 400 318 C430 298 455 312 485 296 C515 280 545 292 575 278 C605 264 630 272 660 260 C690 248 720 258 750 246 C775 236 790 244 800 238 L800 520 Z"/>
    <path d="M60 520 C75 480 100 488 120 462 C140 438 165 448 185 428 C205 410 230 418 250 402 L250 520 Z"/>
    <path d="M470 520 C480 488 500 492 520 472 C540 454 560 462 580 448 L580 520 Z"/>
    <path d="M700 520 C710 496 730 500 745 484 C760 470 775 478 790 470 L790 520 Z"/>
  </g>
  <rect y="520" width="800" height="80" fill="#2c2f3e"/>
  <path d="M0 522 Q120 505 240 518 T480 514 T720 518 L800 514 L800 530 L0 530 Z" fill="#5a5f72" opacity="0.7"/>
  <g fill="#ffd9a0" opacity="0.3">
    <path d="M40 545 C50 530 58 532 66 540 C74 548 80 546 88 538 C96 530 104 534 108 542 L108 545 Z"/>
    <path d="M380 560 C392 542 402 546 412 556 C420 564 430 560 440 550 C450 540 460 546 464 556 L464 560 Z"/>
    <path d="M600 540 C608 528 616 530 624 536 C632 542 640 540 648 532 C656 524 664 528 668 536 L668 540 Z"/>
  </g>
</svg>"""

_FEW_SHOT_B = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 600" width="500" height="600">
  <defs>
    <linearGradient id="skyB" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#dceaf5"/><stop offset="100%" stop-color="#fdf6e3"/>
    </linearGradient>
    <radialGradient id="leafB" cx="0.4" cy="0.35" r="0.75">
      <stop offset="0%" stop-color="#8fce52"/><stop offset="100%" stop-color="#3f7d2a"/>
    </radialGradient>
    <radialGradient id="leafDarkB" cx="0.4" cy="0.35" r="0.75">
      <stop offset="0%" stop-color="#5f9e40"/><stop offset="100%" stop-color="#2c5a1e"/>
    </radialGradient>
    <linearGradient id="trunkB" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#6b4a2f"/><stop offset="45%" stop-color="#8a6140"/>
      <stop offset="100%" stop-color="#4e3520"/>
    </linearGradient>
    <filter id="softB"><feGaussianBlur stdDeviation="7"/></filter>
  </defs>

  <rect width="500" height="600" fill="url(#skyB)"/>
  <path d="M0 430 C60 380 140 390 200 350 C260 315 330 330 380 300 C430 272 465 285 500 265 L500 600 L0 600 Z" fill="#cfe3b8"/>
  <ellipse cx="90" cy="120" rx="60" ry="16" fill="#fff" opacity="0.75" filter="url(#softB)"/>
  <ellipse cx="330" cy="90" rx="80" ry="18" fill="#fff" opacity="0.7" filter="url(#softB)"/>

  <path d="M240 380 C235 320 225 280 232 240 C238 205 230 180 246 140 C256 115 268 95 282 70 L284 62 C300 88 308 118 310 150 C314 190 302 225 300 260 C298 290 306 330 296 380 Z" fill="url(#trunkB)"/>
  <path d="M252 250 C258 230 262 216 270 205 C276 194 272 186 262 184 C258 182 254 184 252 190 L252 200 Z" fill="#7a5638"/>
  <path d="M296 180 C310 160 322 155 330 162 C338 168 336 178 326 186 C314 194 302 194 296 188 Z" fill="#7a5638"/>
  <path d="M232 300 C220 285 210 280 204 286 C198 292 202 302 214 310 C224 316 230 314 232 308 Z" fill="#7a5638"/>

  <g fill="url(#leafB)" filter="url(#shadowB)">
    <path d="M150 230 C120 200 100 160 118 120 C132 88 170 74 200 88 C220 97 228 120 222 146 C232 118 258 100 288 108 C318 116 334 144 326 172 C320 194 298 206 276 204 C296 216 300 238 284 254 C266 272 238 268 228 248 C224 262 210 272 194 268 C178 264 170 250 176 236 C166 244 154 244 150 230 Z"/>
  </g>
  <g fill="url(#leafDarkB)" opacity="0.85">
    <path d="M260 120 C238 96 242 64 266 48 C288 34 318 44 328 66 C336 86 324 106 304 112 C320 104 338 112 342 130 C346 150 330 164 312 162 C326 172 330 190 318 204 C302 222 276 216 268 200 C262 214 248 220 234 214 C222 208 218 194 226 182 C216 188 204 186 198 176 C192 166 196 154 208 150 C194 146 188 132 194 118 C200 104 216 100 226 110 C222 98 226 84 238 78 C250 72 262 78 264 90 C258 82 252 78 250 84 C248 90 252 96 260 100 Z"/>
  </g>
  <g fill="#b8e07a" opacity="0.6">
    <circle cx="180" cy="150" r="8"/><circle cx="200" cy="120" r="6"/>
    <circle cx="290" cy="130" r="9"/><circle cx="310" cy="160" r="7"/>
    <circle cx="240" cy="190" r="6"/><circle cx="270" cy="220" r="8"/>
    <circle cx="160" cy="200" r="5"/><circle cx="330" cy="110" r="5"/>
  </g>
  <g fill="#2c5a1e" opacity="0.5">
    <path d="M170 260 C160 250 154 238 160 228 C166 220 176 224 178 234 C180 244 176 254 170 260 Z"/>
    <path d="M320 240 C312 232 310 222 316 214 C322 208 330 212 330 220 C330 230 326 236 320 240 Z"/>
  </g>
  <g fill="#8a6140" opacity="0.4">
    <path d="M248 350 C244 342 246 334 252 330 C258 326 264 330 262 338 C260 346 254 350 248 350 Z"/>
    <path d="M286 320 C282 314 284 308 290 306 C296 304 300 308 298 314 C296 320 290 322 286 320 Z"/>
  </g>
</svg>"""

_FEW_SHOT_LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <g fill="none" stroke="#000000" stroke-linecap="round" stroke-linejoin="round">
    <path d="M110 150 C110 110 150 90 200 90 C250 90 290 110 290 150 L290 210 C290 260 250 290 200 290 C150 290 110 260 110 210 Z" stroke-width="6"/>
    <path d="M290 160 C330 160 340 190 330 220 C322 244 305 252 292 248" stroke-width="6"/>
    <path d="M80 300 C80 285 320 285 320 300 C320 322 250 336 200 336 C150 336 80 322 80 300 Z" stroke-width="5"/>
    <path d="M170 70 C160 45 180 30 170 10" stroke-width="4"/>
    <path d="M200 60 C188 40 212 25 200 5" stroke-width="4"/>
    <path d="M230 70 C222 50 238 38 230 18" stroke-width="4"/>
    <path d="M60 130 C30 120 25 145 55 150 C40 175 60 185 80 175" stroke-width="3"/>
    <path d="M340 130 C370 120 375 145 345 150 C360 175 340 185 320 175" stroke-width="3"/>
  </g>
</svg>"""

_FEW_SHOT = _FEW_SHOT_A + "\n" + _FEW_SHOT_B

_VASS_ROOT = None


def _get_vass_root():
    global _VASS_ROOT
    if _VASS_ROOT is None:
        _VASS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    return _VASS_ROOT


def _ai_config():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(_get_vass_root(), "config", "settings.ini"), encoding="utf-8")
    return {
        "url": cfg.get("ai", "url", fallback="http://127.0.0.1:8080/v1").rstrip("/"),
        "model": cfg.get("ai", "model", fallback=""),
    }


def _call_llm(prompt, max_tokens=4096, reasoning=False):
    cfg = _ai_config()
    if not cfg["model"]:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url=cfg["url"], api_key="not-needed")
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=max_tokens,
        extra_body={"disable_thinking": not reasoning},
    )
    text = (resp.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:svg|xml)?\s*", "", text).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    m = re.search(r"<svg[\s\S]*?</svg>", text)
    if m:
        return m.group(0)
    if "</svg>" in text:
        return text
    # truncated output: repair by closing at the last complete element
    for marker in ("/>", "</g>", "</defs>", "</path>", "</circle>", "</ellipse>"):
        idx = text.rfind(marker)
        if idx != -1:
            repaired = text[:idx + len(marker)] + "</svg>"
            if _validate_xml(repaired):
                return repaired
    return ""


def _validate_xml(svg):
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(svg)
        return True
    except Exception:
        return False


def _complexity(svg):
    paths = len(re.findall(r"<path\b", svg))
    curves = len(re.findall(r"[CSQ]\s*[\d.\s\-]+", svg))
    gradients = len(re.findall(r"<(?:linear|radial)Gradient\b", svg))
    filters = len(re.findall(r"<filter\b", svg))
    circles = len(re.findall(r"<circle\b", svg))
    ellipses = len(re.findall(r"<ellipse\b", svg))
    rects = len(re.findall(r"<rect\b", svg))
    elements = paths + circles + ellipses + rects + \
        len(re.findall(r"<g\b", svg)) + len(re.findall(r"<polygon\b", svg))
    path_ds = re.findall(r'<path\b[^>]*\bd="([^"]+)"', svg)
    cmds_per_path = [len(re.findall(r"[MmLlHhVvCcSsQqTtAaZz]", d)) for d in path_ds]
    avg_cmds = sum(cmds_per_path) / len(cmds_per_path) if cmds_per_path else 0.0
    long_paths = sum(1 for n in cmds_per_path if n >= 15)
    has_stroke_attr = bool(re.search(r"\bstroke=\"[^\"]+\"", svg))
    stroked = paths if has_stroke_attr else 0
    return {"paths": paths, "curves": curves, "gradients": gradients,
            "filters": filters, "elements": elements,
            "avg_cmds": round(avg_cmds, 1), "long_paths": long_paths,
            "stroked": stroked}


def _is_rich(c, style="detailed"):
    """Complexity thresholds — always demanding; realistic/detailed stricter.
    logo: stroke-based check (no gradients required)."""
    if style == "logo":
        return (c["paths"] >= 8 and c["stroked"] >= 6
                and c["avg_cmds"] >= 6 and c["long_paths"] >= 2)
    if style in ("realistic", "detailed"):
        return (c["paths"] >= 6 and c["elements"] >= 20 and c["gradients"] >= 2
                and c["long_paths"] >= 4 and c["avg_cmds"] >= 8)
    return (c["paths"] >= 5 and c["elements"] >= 15 and c["gradients"] >= 1
            and c["long_paths"] >= 2 and c["avg_cmds"] >= 6)


def _build_scene_map(description, width, height, style):
    """Step 1 of the 2-pass pipeline: plan the scene before drawing it."""
    preset = _STYLE_PRESETS.get(style, _STYLE_PRESETS["detailed"])
    prompt = f"""You are an SVG art director. Plan a detailed scene for this SDXL prompt:

{description} {preset}

Return ONLY a JSON object (no preamble, no code fences) with this exact structure:
{{
  "composition": "short description of layout and focal point",
  "palette": ["#hex", ... 5-8 colors],
  "light": "light source direction and mood",
  "elements": [
    {{"role": "background|midground|foreground|subject|detail|lighting|texture",
      "description": "what it is, shape notes, position hint, relative size",
      "organic": true/false, "asymmetry": true/false}}
  ]
}}
Rules: at least 8 elements; subjects must be organic and asymmetric (no perfect circles, no symmetry);
include texture details and at least 2 lighting elements; sizes must vary (large + medium + small)."""

    text = _call_llm(prompt, max_tokens=1600, reasoning=True)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _build_prompt(description, width, height, style, scene_map=None):
    preset = _STYLE_PRESETS.get(style, _STYLE_PRESETS["detailed"])
    full = f"{description} {preset}".strip()
    rules = []
    matched = set()
    for pattern, instruction in _KEYWORD_RULES:
        if re.search(pattern, full.lower()):
            rules.append(f"- {instruction}")
            matched.add(pattern)
    if not matched:
        rules.append("- " + _KEYWORD_RULES[0][1])
    rules.append("- Every main shape MUST be a path with 10-30 control points "
                 "(many C/S commands); paths with only 1-2 curves are FORBIDDEN for "
                 "the main subject.")
    rules.append("- Organic irregularity is mandatory: no perfect symmetry, no "
                 "perfect circles/ellipses as main shapes, vary angles, slopes and proportions.")
    rules.append("- Asymmetry: subjects slightly off-center, irregular edges, varied sizes.")
    rules.append("- Layered shading: overlapping shapes with varying opacity to model surfaces.")
    rules.append("- Consistent light direction: all shadows and highlights from the same source.")
    rules.append("- Texture: dotted patterns, dashed lines, small marks to break flat surfaces.")
    if style == "logo":
        rules = [
            "- Transparent background: NO background rectangle at all",
            "- All shapes use fill='none' with a single stroke color "
            "(default #000000) and varied stroke-width (2-7) for hierarchy",
            "- Every main shape is a path with 8-25 control points; "
            "smooth clean bezier curves",
            "- No gradients, no color palette, no textures",
            "- Balanced composition, generous margins (logo must stand alone)",
        ]
    else:
        rules.append("- Palette: 5-8 harmonized colors; gradients for depth.")

    scene_block = ""
    if scene_map:
        try:
            scene_block = "\nSCENE PLAN (follow it exactly):\n" + json.dumps(scene_map, ensure_ascii=False, indent=1)
        except Exception:
            scene_block = ""

    # style-aware reference: landscape for scene styles, organic subject for
    # flat/minimal, line-art logo for logo (keeps the prompt shorter)
    if style == "logo":
        reference = _FEW_SHOT_LOGO
    elif style in ("realistic", "detailed"):
        reference = _FEW_SHOT_A
    else:
        reference = _FEW_SHOT_B

    return f"""You are an expert SVG illustrator. Create a high-quality, richly detailed SVG image.

SDXL STYLE PROMPT (subject and mood):
{full}

TECHNICAL REQUIREMENTS (mandatory):
- Root element: <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
- <defs> with linearGradient/radialGradient and filters (feGaussianBlur, feDropShadow)
- Organized layers with <g>: background, subject, details, lighting
{chr(10).join(rules)}
- Valid, self-contained XML: no external references, no text outside the <svg> tag
- Keep the SVG under 3000 characters: complex paths, not more elements
- NEVER create a single path longer than ~30 commands: split large shapes into
  several smaller paths so the file always stays complete
- Output ONLY the SVG code: no preamble, no code fences
{scene_block}
REFERENCE STRUCTURE (imitate this level of construction and detail):
{reference}

Scene: {description}"""


def _refine_prompt(svg, description, width, height, style):
    return f"""The following SVG for "{description}" (style: {style}) is NOT complex enough. Rewrite it:

REQUIRED FIXES:
- The paths are too simple (only 1-4 commands each). Rewrite every main shape as a complex path with 10-30 control points (many C/S commands), irregular asymmetric curves.
- Add layered shading: overlapping shapes with varying opacity, soft shadows, consistent light direction.
- Add texture details (dots, dashes, small marks) to break flat surfaces.
- No perfect circles/ellipses/symmetry for the main subject.
- Keep the same subject, dimensions ({width}x{height}) and viewBox.
- Keep it valid XML, output ONLY the SVG code, no preamble, no code fences.

CURRENT SVG:
{svg}"""

def _build_logo_prompt(description, width, height):
    return f"""Create a clean line-art logo from this description: {description}

MANDATORY RULES:
- Transparent background: NO background rectangle, NO filters (no feTurbulence,
  no feDropShadow, no blur, no displacement), NO gradients, NO fills, NO colors,
  NO patterns, NO text
- Every shape is a path: fill="none" stroke="#000000"
  stroke-linecap="round" stroke-linejoin="round"
- stroke-width between 2 and 7, varied for hierarchy
- Each main shape: a path with 8-25 bezier control points (C/S commands),
  smooth fluid curves
- Balanced composition with generous margins (logo must stand alone)
- Root: <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
- Output ONLY the SVG code: no preamble, no code fences

REFERENCE (imitate this exact style — black strokes only):
{_FEW_SHOT_LOGO}

Logo: {description}"""


def _refine_logo_prompt(svg, description, width, height):
    return f"""This logo is NOT pure line art. Rewrite it completely:
- Remove ALL colors, gradients, filters (feTurbulence, feDropShadow, blur...),
  fills and background elements
- Keep ONLY black strokes: every shape is a path with fill="none" stroke="#000000"
- Each main shape must have 8-25 bezier control points, smooth curves
- stroke-width 2-7, varied for hierarchy
- Same subject and dimensions ({width}x{height}), transparent background
- Output ONLY the SVG code, no preamble, no code fences

CURRENT SVG:
{svg}"""



def _save(svg, width, height):
    out_dir = os.path.join(_get_vass_root(), "Allowed_root", "private_svg")
    os.makedirs(out_dir, exist_ok=True)
    name = f"svg_{time.strftime('%Y%m%d_%H%M%S')}.svg"
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path


def generate_svg(description: str, width: int = 800, height: int = 600,
                 style: str = "detailed") -> str:
    description = (description or "").strip()
    if not description:
        return json.dumps({"status": "error", "message": "Empty description"},
                          ensure_ascii=False)
    try:
        width = max(100, min(2000, int(width)))
        height = max(100, min(2000, int(height)))
    except (ValueError, TypeError):
        width, height = 800, 600
    if style not in _STYLE_PRESETS:
        style = "detailed"

    # Step 1: plan the scene (2-pass pipeline); logos skip the scene map
    if style == "logo":
        scene_map = None
        prompt = _build_logo_prompt(description, width, height)
    else:
        scene_map = _build_scene_map(description, width, height, style)
        prompt = _build_prompt(description, width, height, style, scene_map=scene_map)
    svg = _call_llm(prompt, max_tokens=5000)
    if not svg:
        if style == "logo":
            short = _build_logo_prompt(description, width, height) + \
                "\n\nIMPORTANT: keep it compact (under 2500 characters). Finish with </svg>."
        else:
            short = (_build_prompt(description, width, height, style, scene_map=None)
                     + "\n\nIMPORTANT: generate a COMPACT version, under 2500 characters. "
                       "Finish the file with </svg>.")
        svg = _call_llm(short, max_tokens=4096)
    if not svg:
        return json.dumps({"status": "error", "message": "AI call failed"},
                          ensure_ascii=False)

    valid = _validate_xml(svg)
    if not valid:
        svg2 = _call_llm(prompt, max_tokens=6000)
        if svg2 and _validate_xml(svg2):
            svg = svg2
            valid = True
    if not valid:
        return json.dumps({"status": "error", "message": "Invalid or truncated SVG XML after retry"},
                          ensure_ascii=False)

    for _ in range(2):
        c = _complexity(svg)
        if _is_rich(c, style):
            break
        if style == "logo":
            refined = _call_llm(_refine_logo_prompt(svg, description, width, height))
        else:
            refined = _call_llm(_refine_prompt(svg, description, width, height, style))
        if refined and _validate_xml(refined):
            svg = refined
        else:
            break

    c = _complexity(svg)
    path = _save(svg, width, height)
    return json.dumps({
        "status": "ok",
        "path": path,
        "width": width,
        "height": height,
        "complexity": c,
        "tip": f"Open the file in the browser with browser_open on '{path}' to view it.",
    }, ensure_ascii=False)
