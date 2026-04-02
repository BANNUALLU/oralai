from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from PIL import Image
from datetime import datetime
import os, re, base64, tempfile, json

# ── Colour palette ───────────────────────────────────────────
C_HEADER     = colors.HexColor("#0f172a")
C_ACCENT     = colors.HexColor("#2563eb")
C_TEAL       = colors.HexColor("#0891b2")
C_PURPLE     = colors.HexColor("#7c3aed")
C_SURFACE    = colors.HexColor("#f8fafc")
C_SURFACE2   = colors.HexColor("#f1f5f9")
C_BORDER     = colors.HexColor("#e2e8f0")
C_TEXT       = colors.HexColor("#0f172a")
C_MUTED      = colors.HexColor("#64748b")
C_WHITE      = colors.white
C_SUCCESS    = colors.HexColor("#16a34a")
C_SUCCESS_BG = colors.HexColor("#f0fdf4")
C_SUCCESS_BD = colors.HexColor("#bbf7d0")
C_WARN_BG    = colors.HexColor("#fffbeb")
C_WARN_BD    = colors.HexColor("#fcd34d")
C_WARN_TX    = colors.HexColor("#78350f")

COND_COLOR  = {"malaligned": colors.HexColor("#f59e0b"), "stains": colors.HexColor("#ef4444"),
               "caries": colors.HexColor("#f97316"), "pit_fissure": colors.HexColor("#8b5cf6"),
               "none": colors.HexColor("#16a34a")}
COND_BG     = {"malaligned": colors.HexColor("#fffbeb"), "stains": colors.HexColor("#fef2f2"),
               "caries": colors.HexColor("#fff7ed"), "pit_fissure": colors.HexColor("#f5f3ff"),
               "none": colors.HexColor("#f0fdf4")}
COND_BD     = {"malaligned": colors.HexColor("#fde68a"), "stains": colors.HexColor("#fecaca"),
               "caries": colors.HexColor("#fed7aa"), "pit_fissure": colors.HexColor("#ddd6fe"),
               "none": colors.HexColor("#bbf7d0")}
COND_LABEL  = {"malaligned": "Malaligned Tooth", "stains": "Stains", "caries": "Caries",
               "pit_fissure": "Pit & Fissure Caries", "none": "No Issues Detected"}

FONTS_DIR = "static/fonts"

LANG_FONT_MAP = {
    "English":   "NotoSans-Regular.ttf",
    "Hindi":     "NotoSansDevanagari-Regular.ttf",
    "Marathi":   "NotoSansDevanagari-Regular.ttf",
    "Telugu":    "NotoSansTelugu-Regular.ttf",
    "Tamil":     "NotoSansTamil-Regular.ttf",
    "Kannada":   "NotoSansKannada-Regular.ttf",
    "Malayalam": "NotoSansMalayalam-Regular.ttf",
    "Bengali":   "NotoSansBengali-Regular.ttf",
    "Arabic":    "NotoSansArabic-Regular.ttf",
}

NON_LATIN_LANGUAGES = {
    "Hindi", "Marathi", "Telugu", "Tamil",
    "Kannada", "Malayalam", "Bengali", "Arabic"
}


# ══════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════

def sanitize(text):
    if not isinstance(text, str):
        text = str(text)
    for ch, rep in {"\u2013":"-","\u2014":"-","\u2018":"'","\u2019":"'",
                    "\u201c":'"',"\u201d":'"',"\u2022":"-","\u2026":"...",
                    "\u00a0":" ","\u200b":"","\u2212":"-","\u00d7":"x","\u00b0":" deg"}.items():
        text = text.replace(ch, rep)
    return text

sanitize_structural = sanitize

def clean_markdown(text, language="English"):
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
    text = re.sub(r'^[-=]{2,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = text.replace('`', '')
    if language not in NON_LATIN_LANGUAGES:
        text = re.sub(r'\?{2,}', '', text)
        text = re.sub(r'^[-_=?#*]+$', '', text, flags=re.MULTILINE)
    return re.sub(r'  +', ' ', text).strip()

def wrap_text(text, max_chars=82):
    words = text.split()
    lines, line = [], ""
    for w in words:
        if len(line)+len(w)+1 <= max_chars:
            line = (line+" "+w).strip()
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines

def _esc(text):
    """HTML-escape text (preserves non-ASCII Unicode)."""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def _img_b64(path):
    """Return a data-URI for an image file, or empty string."""
    if not path or not os.path.exists(path):
        return ""
    ext  = os.path.splitext(path)[1].lower().lstrip('.')
    mime = {'jpg':'jpeg','jpeg':'jpeg','png':'png','gif':'gif','webp':'webp'}.get(ext,'png')
    with open(path,'rb') as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:image/{mime};base64,{data}"


# ══════════════════════════════════════════════════════════════
#  WEASYPRINT HTML BUILDER  (pages 2+)
# ══════════════════════════════════════════════════════════════

def _management_html():
    """Build the management section HTML (photos as base64)."""
    config_path = "static/management/config.json"
    if not os.path.exists(config_path):
        return ""
    try:
        with open(config_path) as f:
            members = json.load(f)
    except Exception:
        return ""
    if not members:
        return ""

    rows = ""
    for i in range(0, len(members), 3):
        row   = members[i:i+3]
        cards = ""
        for m in row:
            img_path = os.path.join("static", "management", m.get("file", ""))
            b64 = _img_b64(img_path)
            if b64:
                photo_tag = f'<img class="mgmt-photo" src="{b64}" alt="">'
            else:
                photo_tag = '<div class="mgmt-photo-placeholder"></div>'
            cards += f"""
              <div class="mgmt-card">
                {photo_tag}
                <div class="mgmt-name">{_esc(m.get('name',''))}</div>
                <div class="mgmt-title">{_esc(m.get('title',''))}</div>
              </div>"""
        rows += f'<div class="mgmt-row">{cards}</div>\n'

    return f"""
    <div class="mgmt-section">
      <div class="mgmt-head">Swarnandhra College of Engineering and Technology &#8212; Management</div>
      {rows}
    </div>"""


def generate_analysis_html(claude_analysis, language, name, age, gender,
                            report_id, logo_path, total_pages):
    """
    Build a complete HTML document for the analysis pages.
    WeasyPrint will convert it to PDF — Pango/HarfBuzz handles Telugu/Hindi etc.
    """
    font_file = LANG_FONT_MAP.get(language, "NotoSans-Regular.ttf")
    font_path = os.path.join(FONTS_DIR, font_file)
    font_abs  = os.path.abspath(font_path)

    # English font always available for header/footer labels
    en_font_path = os.path.join(FONTS_DIR, "NotoSans-Regular.ttf")
    en_font_abs  = os.path.abspath(en_font_path)

    logo_src = _img_b64(logo_path)
    date_str = datetime.now().strftime('%d %b %Y')

    # ── Parse analysis into HTML fragments ──────────────────
    cleaned = clean_markdown(claude_analysis, language=language)
    content_html = ""
    for raw in cleaned.split("\n"):
        line = raw.strip()
        if not line:
            content_html += '<div class="spacer"></div>\n'
        elif re.match(r'^\d+\.\s+[^\s]', line) and len(line) < 120:
            content_html += f'<div class="sec-head">{_esc(line)}</div>\n'
        elif line.startswith(("- ", "• ", "* ")):
            content_html += f'<div class="bullet">{_esc(line[2:].strip())}</div>\n'
        else:
            content_html += f'<p class="body">{_esc(line)}</p>\n'

    mgmt_html = _management_html()

    # ── Arabic needs RTL direction ───────────────────────────
    dir_attr  = 'rtl' if language == "Arabic" else 'ltr'
    text_align = 'right' if language == "Arabic" else 'left'

    # ── Logo in header ───────────────────────────────────────
    logo_img_tag = f'<img id="hdr-logo" src="{logo_src}" alt="logo">' if logo_src else ''

    html = f"""<!DOCTYPE html>
<html lang="{language}" dir="{dir_attr}">
<head>
<meta charset="UTF-8">
<style>

/* ── Fonts ─────────────────────────────────────────────── */
@font-face {{
  font-family: 'NativeLang';
  src: url('file://{font_abs}');
  font-weight: normal; font-style: normal;
}}
@font-face {{
  font-family: 'EnFont';
  src: url('file://{en_font_abs}');
  font-weight: normal; font-style: normal;
}}

/* ── Page layout ────────────────────────────────────────── */
@page {{
  size: 210mm 297mm;
  margin: 28mm 10mm 18mm 10mm;

  @top-left {{
    content: element(page-header);
    margin-left: -10mm;
    width: 210mm;
    height: 26mm;
    vertical-align: top;
  }}

  @bottom-left {{
    content: "OralAI \2014 AI Oral Health Screening \00a0|\00a0 www.oralai.site";
    background: #0f172a;
    color: #ffffff;
    font-family: 'EnFont', Helvetica, Arial;
    font-size: 8pt;
    font-weight: bold;
    height: 16mm;
    width: 130mm;
    margin-left: -10mm;
    padding-left: 8mm;
    vertical-align: middle;
  }}

  @bottom-right {{
    content: "ID: {report_id[:14]} \00a0|\00a0 {date_str} \00a0|\00a0 Page " counter(page) " of {total_pages}";
    background: #0f172a;
    color: #94a3b8;
    font-family: 'EnFont', Helvetica, Arial;
    font-size: 7pt;
    height: 16mm;
    width: 90mm;
    margin-right: -10mm;
    padding-right: 4mm;
    vertical-align: middle;
    text-align: right;
  }}
}}

/* ── Reset ──────────────────────────────────────────────── */
* {{ box-sizing: border-box; }}

body {{
  font-family: 'NativeLang', 'Noto Sans', sans-serif;
  font-size: 9pt;
  color: #0f172a;
  line-height: 1.55;
  text-align: {text_align};
  direction: {dir_attr};
}}

/* ── Running page header ────────────────────────────────── */
#page-header {{
  position: running(page-header);
  width: 210mm;
  height: 26mm;
  background: #0f172a;
  display: flex;
  flex-direction: column;
}}
#hdr-body {{
  display: flex;
  align-items: center;
  flex: 1;
  padding: 0 0 0 0;
}}
#hdr-teal {{
  width: 3mm;
  min-width: 3mm;
  height: 24mm;
  background: #0891b2;
  align-self: flex-start;
}}
#hdr-content {{
  display: flex;
  align-items: center;
  gap: 3mm;
  padding: 2mm 0 0 2mm;
  flex: 1;
}}
#hdr-logo {{
  height: 18mm;
  width: auto;
  display: block;
}}
#hdr-sep {{
  width: 0.3mm;
  height: 16mm;
  background: #334155;
}}
#hdr-text {{
  display: flex;
  flex-direction: column;
  gap: 1mm;
}}
#hdr-title {{
  color: #ffffff;
  font-family: 'EnFont', Helvetica, Arial;
  font-size: 13pt;
  font-weight: bold;
}}
#hdr-sub {{
  color: #a78bfa;
  font-family: 'EnFont', Helvetica, Arial;
  font-size: 7pt;
}}
#hdr-purple {{
  height: 1.5mm;
  width: 100%;
  background: #7c3aed;
}}

/* ── Content elements ───────────────────────────────────── */
.spacer {{ height: 3mm; }}

.sec-head {{
  background: #2563eb;
  color: #ffffff;
  font-size: 10pt;
  padding: 2mm 3mm;
  margin: 5mm 0 3mm 0;
  page-break-inside: avoid;
  page-break-after: avoid;
}}

.bullet {{
  padding: 1.5mm 0 1.5mm 7mm;
  position: relative;
  page-break-inside: avoid;
}}
.bullet::before {{
  content: '\2022';
  color: #2563eb;
  font-size: 10pt;
  position: absolute;
  left: 1mm;
  top: 1mm;
}}

.body {{
  margin: 1.5mm 0;
  page-break-inside: avoid;
}}

/* ── Disclaimer ─────────────────────────────────────────── */
.disclaimer {{
  background: #fffbeb;
  border: 0.4mm solid #fcd34d;
  padding: 2mm 3mm;
  font-family: 'EnFont', Helvetica, Arial;
  font-size: 7pt;
  color: #78350f;
  font-style: italic;
  margin: 5mm 0;
  page-break-inside: avoid;
}}

/* ── Management section ─────────────────────────────────── */
.mgmt-section {{
  page-break-inside: avoid;
  margin-top: 5mm;
}}
.mgmt-head {{
  background: #0f172a;
  color: #ffffff;
  font-family: 'EnFont', Helvetica, Arial;
  font-size: 9pt;
  font-weight: bold;
  padding: 2mm 3mm 2mm 5mm;
  border-left: 2.5mm solid #0891b2;
  margin-bottom: 5mm;
}}
.mgmt-row {{
  display: flex;
  gap: 5mm;
  margin-bottom: 5mm;
}}
.mgmt-card {{
  width: 58mm;
  text-align: center;
}}
.mgmt-photo {{
  width: 28mm;
  height: 28mm;
  border-radius: 50%;
  border: 0.7mm solid #2563eb;
  object-fit: cover;
  display: block;
  margin: 0 auto 2mm auto;
}}
.mgmt-photo-placeholder {{
  width: 28mm;
  height: 28mm;
  border-radius: 50%;
  background: #e2e8f0;
  border: 0.7mm solid #2563eb;
  display: block;
  margin: 0 auto 2mm auto;
}}
.mgmt-name {{
  font-family: 'EnFont', Helvetica, Arial;
  font-size: 8pt;
  font-weight: bold;
  color: #0f172a;
}}
.mgmt-title {{
  font-family: 'EnFont', Helvetica, Arial;
  font-size: 6.5pt;
  color: #64748b;
  margin-top: 1mm;
  line-height: 1.4;
}}

</style>
</head>
<body>

<!-- ── Running page header (pulled out of flow by WeasyPrint) ── -->
<div id="page-header">
  <div id="hdr-body">
    <div id="hdr-teal"></div>
    <div id="hdr-content">
      {logo_img_tag}
      <div id="hdr-sep"></div>
      <div id="hdr-text">
        <span id="hdr-title">AI Detailed Analysis</span>
        <span id="hdr-sub">Language: {_esc(language)} &nbsp;|&nbsp; Observing all 3 dental images</span>
      </div>
    </div>
  </div>
  <div id="hdr-purple"></div>
</div>

<!-- ── Analysis content ─────────────────────────────────────── -->
{content_html}

<!-- ── Disclaimer ──────────────────────────────────────────── -->
<div class="disclaimer">
  This is an AI-based screening tool and does not replace a professional dental diagnosis. Please consult a dentist.
</div>

<!-- ── Management section ──────────────────────────────────── -->
{mgmt_html}

</body>
</html>"""

    return html


def generate_analysis_weasyprint(claude_analysis, language, name, age, gender,
                                  report_id, logo_path, total_pages):
    """Render HTML → PDF via WeasyPrint (Pango/HarfBuzz = correct Indic shaping)."""
    try:
        from weasyprint import HTML
        import logging
        logging.getLogger('weasyprint').setLevel(logging.ERROR)
    except ImportError:
        raise RuntimeError(
            "weasyprint not installed.\n"
            "Run: sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b\n"
            "     pip install weasyprint --break-system-packages"
        )

    html_str  = generate_analysis_html(
        claude_analysis, language, name, age, gender,
        report_id, logo_path, total_pages
    )
    temp_path = f"static/reports/temp_analysis_{report_id}.pdf"
    HTML(string=html_str, base_url=os.getcwd()).write_pdf(temp_path)
    print(f"[WeasyPrint] OK → {temp_path}")
    return temp_path


# ══════════════════════════════════════════════════════════════
#  PAGE 1  (ReportLab — unchanged)
# ══════════════════════════════════════════════════════════════

def get_face_photo_path(screening_id, report_id):
    if screening_id:
        for d in ["uploads", "results"]:
            p = os.path.join("static", d, f"{screening_id}_face.jpg")
            if os.path.exists(p): return p
    p = os.path.join("static", "results", f"{report_id}_face.jpg")
    return p if os.path.exists(p) else None

def draw_footer_rl(c, W, report_id, page_num, total_pages):
    c.setFillColor(C_HEADER); c.rect(0, 0, W, 42, fill=1, stroke=0)
    c.setFillColor(C_TEAL);   c.rect(0, 0, 6, 42, fill=1, stroke=0)
    c.setFillColor(C_WHITE);  c.setFont("Helvetica-Bold", 10)
    c.drawString(18, 22, "OralAI  -  AI Oral Health Screening  |  www.oralai.site")
    c.setFont("Helvetica", 9); c.setFillColor(colors.HexColor("#94a3b8"))
    c.drawRightString(W-16, 16,
        f"Report ID: {report_id}   |   {datetime.now().strftime('%d %b %Y')}   |   Page {page_num} of {total_pages}")

def draw_section_bar_rl(c, W, y, title, color=None):
    c.setFillColor(color or C_ACCENT); c.rect(0, y-26, W, 26, fill=1, stroke=0)
    c.setFillColor(C_WHITE); c.setFont("Helvetica-Bold", 11)
    c.drawString(28, y-17, title); return y-26

def draw_patient_info_bar(c, W, H, header_h, name, age, gender, phone, now, face_photo_path=None):
    bt = H-header_h; bh = 54
    c.setFillColor(C_SURFACE2); c.rect(0, bt-bh, W, bh, fill=1, stroke=0)
    c.setStrokeColor(C_BORDER); c.setLineWidth(0.8); c.line(0, bt-bh, W, bt-bh)
    pw, ph = 40, 44; px = W-pw-14; py = bt-bh+5
    if face_photo_path and os.path.exists(face_photo_path):
        c.setStrokeColor(C_BORDER); c.setLineWidth(1)
        c.roundRect(px-2, py-2, pw+4, ph+4, 4, fill=0, stroke=1)
        try: c.drawImage(face_photo_path, px, py, width=pw, height=ph,
                         preserveAspectRatio=True, mask="auto")
        except: _draw_face_placeholder(c, px, py, pw, ph)
    else:
        _draw_face_placeholder(c, px, py, pw, ph)
    def ip(label, value, x, y):
        c.setFillColor(C_MUTED); c.setFont("Helvetica", 9)
        lw = c.stringWidth(label, "Helvetica", 9); c.drawString(x, y, label)
        c.setFillColor(C_TEXT); c.setFont("Helvetica-Bold", 10); c.drawString(x+lw+3, y, value)
    ip("Name:",  f"{name}  ({age} / {gender})", 28, bt-22)
    ip("Phone:", phone, 28, bt-38); ip("Date:", now, 220, bt-38)
    return bt-bh

def _draw_face_placeholder(c, x, y, w, h):
    c.setFillColor(colors.HexColor("#e2e8f0")); c.roundRect(x, y, w, h, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#94a3b8")); c.setFont("Helvetica", 7)
    c.drawCentredString(x+w/2, y+h/2-3, "No"); c.drawCentredString(x+w/2, y+h/2-11, "Photo")

def _build_page1(c, W, H, header_h, name, age, gender, phone, now,
                 logo_path, face_photo_path, img_parts, img_w, img_h,
                 card_h, gap, pill_colors, detected_labels,
                 recommendations, no_issues, report_id, total_pages):

    c.setFillColor(C_HEADER); c.rect(0, H-header_h, W, header_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1e3a8a")); c.rect(0, H-header_h, 8, header_h, fill=1, stroke=0)
    if os.path.exists(logo_path):
        ly = H-header_h+(header_h-60)/2
        c.drawImage(logo_path, 20, ly, width=180, height=60,
                    preserveAspectRatio=True, mask="auto")
        c.setStrokeColor(colors.HexColor("#334155")); c.setLineWidth(1)
        c.line(210, H-header_h+14, 210, H-14)
        c.setFillColor(C_WHITE); c.setFont("Helvetica-Bold", 20)
        c.drawString(222, H-header_h+44, "Oral Health Screening Report")
        c.setFillColor(colors.HexColor("#7dd3fc")); c.setFont("Helvetica", 9)
        c.drawString(224, H-header_h+26, "powered by OralAI")
    else:
        c.setFillColor(C_WHITE); c.setFont("Helvetica-Bold", 22)
        c.drawString(30, H-header_h+44, "Oral Health Screening Report")

    bar_bottom = draw_patient_info_bar(c, W, H, header_h, name, age, gender, phone, now,
                                       face_photo_path=face_photo_path)
    cur_y = bar_bottom
    cur_y = draw_section_bar_rl(c, W, cur_y, "  AI SCREENING REPORT")
    card_y = cur_y-14-card_h

    for i, (lbl, fname) in enumerate(img_parts):
        ix = 28+gap+i*(img_w+gap); iy2 = card_y
        c.setFillColor(colors.HexColor("#cbd5e1"))
        c.roundRect(ix+3, iy2-3, img_w, card_h, 10, fill=1, stroke=0)
        c.setFillColor(C_WHITE); c.roundRect(ix, iy2, img_w, card_h, 10, fill=1, stroke=0)
        c.setFillColor(C_SURFACE2); c.roundRect(ix+5, iy2+28, img_w-10, img_h, 8, fill=1, stroke=0)
        ip2 = os.path.join("static", "results", fname)
        if os.path.exists(ip2):
            c.drawImage(ip2, ix+5, iy2+28, width=img_w-10, height=img_h,
                        preserveAspectRatio=True, mask="auto")
        c.setStrokeColor(C_BORDER); c.setLineWidth(0.8)
        c.roundRect(ix, iy2, img_w, card_h, 10, fill=0, stroke=1)
        c.setFillColor(pill_colors[i])
        c.roundRect(ix+14, iy2+7, img_w-28, 17, 8, fill=1, stroke=0)
        c.setFillColor(C_WHITE); c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(ix+img_w/2, iy2+12, lbl)

    cur_y = card_y-18
    detected = [k for k in ["malaligned","stains","caries","pit_fissure"]
                if k in detected_labels]
    if detected:
        c.setFillColor(C_SURFACE2)
        c.roundRect(28, cur_y-10, W-56, 22, 6, fill=1, stroke=0)
        c.setStrokeColor(C_BORDER); c.setLineWidth(0.6)
        c.roundRect(28, cur_y-10, W-56, 22, 6, fill=0, stroke=1)
        lx = 44
        for key in detected:
            col = COND_COLOR[key]; txt = COND_LABEL[key]
            c.setFillColor(col); c.circle(lx+5, cur_y+2, 5, fill=1, stroke=0)
            c.setFillColor(C_TEXT); c.setFont("Helvetica", 9)
            c.drawString(lx+14, cur_y-2, txt)
            lx += c.stringWidth(txt, "Helvetica", 9)+34
        cur_y -= 24

    cur_y -= 4
    cur_y = draw_section_bar_rl(c, W, cur_y, "  TREATMENT RECOMMENDATIONS")
    cur_y -= 8

    if no_issues:
        rt    = recommendations[0]["recommendation"] if recommendations else "No issues detected."
        lines = wrap_text(rt, 76); rh = max(52, 22+len(lines)*14); cur_y -= rh+4
        c.setFillColor(C_SUCCESS_BG); c.roundRect(28, cur_y, W-56, rh, 8, fill=1, stroke=0)
        c.setStrokeColor(C_SUCCESS_BD); c.setLineWidth(1)
        c.roundRect(28, cur_y, W-56, rh, 8, fill=0, stroke=1)
        c.setFillColor(C_SUCCESS); c.rect(28, cur_y, 5, rh, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(42, cur_y+rh-15, "No major oral health issues detected")
        ty = cur_y+rh-29; c.setFillColor(C_MUTED); c.setFont("Helvetica", 9.5)
        for ln in lines: c.drawString(42, ty, ln); ty -= 13
    else:
        for rec in recommendations:
            if rec["label"] == "none": continue
            label    = rec["label"]; conf = rec.get("confidence", 0)
            rt       = rec["recommendation"]; lines = wrap_text(rt, 73)
            rh       = max(56, 30+len(lines)*13)
            col      = COND_COLOR.get(label, C_MUTED)
            bg       = COND_BG.get(label,   C_SURFACE)
            bd       = COND_BD.get(label,   C_BORDER)
            lt       = COND_LABEL.get(label, label.title())
            cur_y   -= rh+8
            c.setFillColor(bg); c.roundRect(28, cur_y, W-56, rh, 8, fill=1, stroke=0)
            c.setStrokeColor(bd); c.setLineWidth(1)
            c.roundRect(28, cur_y, W-56, rh, 8, fill=0, stroke=1)
            c.setFillColor(col); c.rect(28, cur_y, 6, rh, fill=1, stroke=0)
            c.setFillColor(col); c.circle(52, cur_y+rh-18, 8, fill=1, stroke=0)
            c.setFillColor(C_TEXT); c.setFont("Helvetica-Bold", 12)
            c.drawString(68, cur_y+rh-14, lt)
            bx = 68+c.stringWidth(lt, "Helvetica-Bold", 12)+8
            c.setFillColor(col); c.roundRect(bx, cur_y+rh-19, 56, 14, 5, fill=1, stroke=0)
            c.setFillColor(C_WHITE); c.setFont("Helvetica-Bold", 7.5)
            c.drawCentredString(bx+28, cur_y+rh-12, f"{conf:.0%} confidence")
            c.setFillColor(C_TEXT); c.setFont("Helvetica", 9.5)
            ty = cur_y+rh-30
            for ln in lines: c.drawString(68, ty, ln); ty -= 13

    draw_footer_rl(c, W, report_id, 1, total_pages)
    c.save()


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

def generate_pdf(user_data, detected_labels, report_id,
                 recommendations=None, claude_analysis=None, screening_id=None):

    name     = user_data.get("name",     "Patient")
    age      = user_data.get("age",      "N/A")
    gender   = user_data.get("gender",   "N/A")
    phone    = user_data.get("phone",    "N/A")
    language = user_data.get("language", "English")
    now      = datetime.now().strftime("%d %b %Y  %I:%M %p")

    if recommendations is None:
        recommendations = []

    report_path = f"static/reports/{report_id}.pdf"
    logo_path   = "static/logo.png"
    face_photo  = get_face_photo_path(screening_id, report_id)

    img_h = 152; img_w = 152
    gap   = (595.27-56-img_w*3)/4
    card_h = img_h+34
    pill_colors = [C_ACCENT, C_TEAL, C_PURPLE]

    img_parts = (
        [(f"Upper Teeth", f"{screening_id}_upper_yolo.jpg"),
         (f"Front Teeth", f"{screening_id}_front_yolo.jpg"),
         (f"Lower Teeth", f"{screening_id}_lower_yolo.jpg")]
        if screening_id else
        [("Upper Teeth","upper_yolo.jpg"),
         ("Front Teeth","front_yolo.jpg"),
         ("Lower Teeth","lower_yolo.jpg")]
    )

    no_issues = (not recommendations or
                 (len(recommendations)==1 and recommendations[0]["label"]=="none"))

    # ── Page 1 (placeholder total) ───────────────────────────
    c = rl_canvas.Canvas(report_path, pagesize=A4); W, H = A4
    _build_page1(c, W, H, 90, name, age, gender, phone, now,
                 logo_path, face_photo, img_parts, img_w, img_h, card_h, gap,
                 pill_colors, detected_labels, recommendations, no_issues,
                 report_id, total_pages=99)

    if not claude_analysis:
        return report_path

    try:
        from pypdf import PdfWriter, PdfReader

        # ── First pass: count pages ──────────────────────────
        tmp = generate_analysis_weasyprint(
            claude_analysis, language, name, age, gender,
            report_id, logo_path, total_pages=99
        )

        w1 = PdfWriter()
        for p in PdfReader(report_path).pages: w1.add_page(p)
        for p in PdfReader(tmp).pages:         w1.add_page(p)
        actual = len(w1.pages)
        print(f"[PDF] Total pages: {actual}, language={language}")

        # ── Rebuild page 1 with correct total ───────────────
        c2 = rl_canvas.Canvas(report_path, pagesize=A4)
        _build_page1(c2, W, H, 90, name, age, gender, phone, now,
                     logo_path, face_photo, img_parts, img_w, img_h, card_h, gap,
                     pill_colors, detected_labels, recommendations, no_issues,
                     report_id, total_pages=actual)

        # ── Rebuild analysis with correct total ──────────────
        os.remove(tmp)
        tmp2 = generate_analysis_weasyprint(
            claude_analysis, language, name, age, gender,
            report_id, logo_path, total_pages=actual
        )

        # ── Final merge ──────────────────────────────────────
        w2 = PdfWriter()
        for p in PdfReader(report_path).pages: w2.add_page(p)
        for p in PdfReader(tmp2).pages:        w2.add_page(p)
        with open(report_path, "wb") as f:     w2.write(f)
        os.remove(tmp2)
        print(f"[PDF] Saved: {report_path}")

    except Exception as e:
        import traceback
        print(f"[PDF] ERROR: {e}")
        traceback.print_exc()

    return report_path