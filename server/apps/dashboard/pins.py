from django.http import HttpResponse, HttpResponseBadRequest

# === Exacte pin-vorm: jouw pad uit de SVG (viewBox 0 0 256 256) ===
_PROVIDED_PIN_PATH = (
    "M128.18,249.042c-4.252,0-8.151-2.365-10.114-6.137L64.648,140.331c-0.082-0.156-0.159-0.313-0.233-0.474 "
    "C55.837,121.342,47.9,101.865,47.9,84.859c0-20.079,8.655-40.271,23.747-55.4c15.512-15.549,35.68-24.113,56.787-24.113 "
    "c21.099,0,41.188,8.579,56.57,24.155c14.904,15.093,23.453,35.271,23.454,55.358c0,18.868-9.282,38.867-16.062,53.47l-0.707,1.526 "
    "c-0.07,0.152-0.146,0.306-0.224,0.453l-53.159,102.574c-1.959,3.778-5.859,6.151-10.116,6.156 "
    "C128.188,249.042,128.184,249.042,128.18,249.042z"
)

def _escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&apos;")
    )

def _norm_hex(s: str, default: str) -> str:
    # accepteert 3 of 6 hex, met of zonder #
    s = (s or "").strip().lstrip("#")
    if len(s) not in (3, 6):
        return default.lstrip("#")
    if len(s) == 3:
        s = "".join(c*2 for c in s)
    return s

def _pin_svg(letter: str,
             bg_hex: str, fg_hex: str,
             w: int, h: int,
             stroke_hex: str = "2a2a2a",
             stroke_width_units: float = 4.0,
             font_family: str = "Inter,Segoe UI,Arial,sans-serif",
             font_weight: str = "700",
             font_size_units: float = None,
             text_y_units: float = None):
    """
    Bouwt een SVG met jouw exacte pad, geschaald naar width=w, height=h.
    viewBox blijft 0 0 256 256, waardoor het pad exact schaalt.

    font_size_units en text_y_units zijn optioneel en in viewBox-eenheden (0..256).
    Als niet gezet, worden ze automatisch bepaald op basis van tekstlengte.
    """
    pin_hex = _norm_hex(bg_hex or "000000", "000000")
    txt_hex = _norm_hex(fg_hex or "FFFFFF", "FFFFFF")
    stroke_hex = _norm_hex(stroke_hex or "2a2a2a", "2a2a2a")

    # Defaults voor tekstpositie en -grootte, getuned voor dit pad
    # De kop zit grofweg in de bovenste ~120-140 eenheden. Deze waarden geven een nette centrering.
    if font_size_units is None:
        if len(letter) <= 2:   font_size_units = 64
        elif len(letter) == 3: font_size_units = 54
        else:                  font_size_units = 46
    if text_y_units is None:
        text_y_units = 110  # optisch midden van de kop

    letter = _escape_xml(letter)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
      width="{w}" height="{h}" viewBox="0 0 256 256" preserveAspectRatio="xMidYMid meet">
  <defs>
    <filter id="shadow" x="-15%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.28"/>
    </filter>
  </defs>

  <!-- lichaam van de pin -->
  <path d="{_PROVIDED_PIN_PATH}"
        fill="#{pin_hex}"
        stroke="#{stroke_hex}"
        stroke-width="{stroke_width_units}"
        filter="url(#shadow)"/>

  <!-- tekst -->
  <text x="128" y="{text_y_units}"
        text-anchor="middle" dominant-baseline="middle"
        font-family="{font_family}" font-weight="{font_weight}"
        font-size="{font_size_units}" fill="#{txt_hex}">{letter}</text>
</svg>"""
    return svg

def chart_pin(request):
    """
    Nieuwe parameters:
      /chart?letter=A&bgcolor=00008B&color=FFFFFF&chs=48x64&format=svg
      Optioneel: &stroke=333333&sw=4 (stroke width in viewBox units)
                 &fs=64 (font-size in viewBox units)
                 &ty=110 (text y in viewBox units)

    Backward-compatible Google-stijl:
      /chart?chst=d_map_pin_letter&chld=A|00008B|FFFFFF&chs=48x64&format=svg

    Let op: dit endpoint geeft exact SVG terug. PNG kan later, maar vereist een rasterizer.
    """
    fmt = (request.GET.get("format") or "svg").lower()

    # nieuwe param-namen
    letter = request.GET.get("letter") or request.GET.get("text")
    bg = request.GET.get("bgcolor")
    fg = request.GET.get("color")
    stroke = request.GET.get("stroke")  # optioneel
    sw = request.GET.get("sw")          # optioneel stroke width (viewBox units)
    fs = request.GET.get("fs")          # optioneel font-size (viewBox units)
    ty = request.GET.get("ty")          # optioneel text-y (viewBox units)

    # fallback naar oude Google-stijl
    if letter is None and request.GET.get("chst") == "d_map_pin_letter":
        chld = request.GET.get("chld", "")
        parts = chld.split("|")
        letter = (parts[0] if len(parts) > 0 else None)
        bg = (parts[1] if len(parts) > 1 else None)
        fg = (parts[2] if len(parts) > 2 else None)

    if not letter:
        return HttpResponseBadRequest("Missing letter")

    chs = (request.GET.get("chs") or "21x34").lower()
    try:
        w, h = [int(x) for x in chs.split("x")]
    except Exception:
        w, h = 21, 34

    if fmt != "svg":
        return HttpResponseBadRequest("Only format=svg is supported for the exact provided path")

    # optionele numerieke overrides
    stroke_w = float(sw) if sw is not None else 4.0
    font_size_units = float(fs) if fs is not None else None
    text_y_units = float(ty) if ty is not None else None

    svg = _pin_svg(
        letter=letter,
        bg_hex=bg or "000000",
        fg_hex=fg or "FFFFFF",
        w=w, h=h,
        stroke_hex=stroke or "2a2a2a",
        stroke_width_units=stroke_w,
        font_size_units=font_size_units,
        text_y_units=text_y_units,
    )
    resp = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8")
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp
