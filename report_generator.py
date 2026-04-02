from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from fpdf import FPDF
from datetime import datetime
import os
import re
import base64
import tempfile


# ── Colour palette ───────────────────────────────────────────────
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

COND_COLOR = {
    "malaligned":  colors.HexColor("#f59e0b"),
    "stains":      colors.HexColor("#ef4444"),
    "caries":      colors.HexColor("#f97316"),
    "pit_fissure": colors.HexColor("#8b5cf6"),
    "none":        colors.HexColor("#16a34a"),
}
COND_BG = {
    "malaligned":  colors.HexColor("#fffbeb"),
    "stains":      colors.HexColor("#fef2f2"),
    "caries":      colors.HexColor("#fff7ed"),
    "pit_fissure": colors.HexColor("#f5f3ff"),
    "none":        colors.HexColor("#f0fdf4"),
}
COND_BD = {
    "malaligned":  colors.HexColor("#fde68a"),
    "stains":      colors.HexColor("#fecaca"),
    "caries":      colors.HexColor("#fed7aa"),
    "pit_fissure": colors.HexColor("#ddd6fe"),
    "none":        colors.HexColor("#bbf7d0"),
}
COND_LABEL = {
    "malaligned":  "Malaligned Tooth",
    "stains":      "Stains",
    "caries":      "Caries",
    "pit_fissure": "Pit & Fissure Caries",
    "none":        "No Issues Detected",
}

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

# Languages that use non-Latin scripts — DO NOT sanitize their content
NON_LATIN_LANGUAGES = {
    "Hindi", "Marathi", "Telugu", "Tamil",
    "Kannada", "Malayalam", "Bengali", "Arabic"
}


def sanitize(text):
    """Sanitize ASCII/Latin special chars only. Never touches Unicode script text."""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2022": "-", "\u2026": "...",
        "\u00a0": " ", "\u200b": "", "\u2212": "-", "\u00d7": "x",
        "\u00b0": " deg",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def sanitize_structural(text):
    """
    For structural/label text (always ASCII) — same as sanitize().
    Use this for headers, footers, labels — never for body content in Indian languages.
    """
    return sanitize(text)


def clean_markdown(text, language="English"):
    """
    Clean markdown formatting.
    For non-Latin languages: only strip markdown symbols, preserve all Unicode characters.
    """
    # Strip markdown heading markers
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # Strip bold/italic markers
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
    # Strip horizontal rules (ASCII only)
    text = re.sub(r'^[-=]{2,}\s*$', '', text, flags=re.MULTILINE)
    # Strip markdown links
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Strip backticks
    text = text.replace('`', '')

    if language not in NON_LATIN_LANGUAGES:
        # For English only: strip lines that are nothing but punctuation/symbols
        text = re.sub(r'\?{2,}', '', text)
        text = re.sub(r'^[-_=?#*]+$', '', text, flags=re.MULTILINE)

    # Collapse multiple spaces (safe for all languages)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def wrap_text(text, max_chars=82):
    words = text.split()
    lines, line = [], ""
    for w in words:
        if len(line) + len(w) + 1 <= max_chars:
            line = (line + " " + w).strip()
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_footer_rl(c, W, report_id, page_num, total_pages):
    c.setFillColor(C_HEADER)
    c.rect(0, 0, W, 42, fill=1, stroke=0)
    c.setFillColor(C_TEAL)
    c.rect(0, 0, 6, 42, fill=1, stroke=0)
    c.setFillColor(C_WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(18, 22, "OralAI  -  AI Oral Health Screening  |  www.oralai.site")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.drawRightString(W - 16, 16,
        f"Report ID: {report_id}   |   {datetime.now().strftime('%d %b %Y')}   |   Page {page_num} of {total_pages}")


def draw_disclaimer_rl(c, W):
    c.setFillColor(C_WARN_BG)
    c.roundRect(28, 50, W - 56, 24, 6, fill=1, stroke=0)
    c.setStrokeColor(C_WARN_BD)
    c.setLineWidth(0.8)
    c.roundRect(28, 50, W - 56, 24, 6, fill=0, stroke=1)
    c.setFillColor(C_WARN_TX)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawCentredString(W / 2, 59,
        "This is an AI-based screening tool and does not replace a professional dental diagnosis. Please consult a dentist.")


def draw_section_bar_rl(c, W, y, title, color=None):
    bg = color or C_ACCENT
    c.setFillColor(bg)
    c.rect(0, y - 26, W, 26, fill=1, stroke=0)
    c.setFillColor(C_WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(28, y - 17, title)
    return y - 26


def get_face_photo_path(screening_id, report_id):
    if screening_id:
        path = os.path.join("static", "uploads", f"{screening_id}_face.jpg")
        if os.path.exists(path):
            print(f"[Face] Found in uploads: {path}")
            return path
        path = os.path.join("static", "results", f"{screening_id}_face.jpg")
        if os.path.exists(path):
            print(f"[Face] Found in results: {path}")
            return path

    path = os.path.join("static", "results", f"{report_id}_face.jpg")
    if os.path.exists(path):
        print(f"[Face] Found by report_id: {path}")
        return path

    print("[Face] No face photo found — placeholder will be used.")
    return None


def draw_patient_info_bar(c, W, H, header_h, name, age, gender, phone, now, face_photo_path=None):
    bar_top = H - header_h
    bar_h   = 54

    c.setFillColor(C_SURFACE2)
    c.rect(0, bar_top - bar_h, W, bar_h, fill=1, stroke=0)
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.8)
    c.line(0, bar_top - bar_h, W, bar_top - bar_h)

    photo_w = 40
    photo_h = 44
    photo_x = W - photo_w - 14
    photo_y = bar_top - bar_h + 5

    if face_photo_path and os.path.exists(face_photo_path):
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(1)
        c.roundRect(photo_x - 2, photo_y - 2, photo_w + 4, photo_h + 4, 4, fill=0, stroke=1)
        try:
            c.drawImage(
                face_photo_path,
                photo_x, photo_y,
                width=photo_w, height=photo_h,
                preserveAspectRatio=True,
                mask="auto"
            )
        except Exception as e:
            print(f"Face photo draw error: {e}")
            _draw_face_placeholder(c, photo_x, photo_y, photo_w, photo_h)
    else:
        _draw_face_placeholder(c, photo_x, photo_y, photo_w, photo_h)

    def info_pair(label, value, x, y):
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 9)
        lw = c.stringWidth(label, "Helvetica", 9)
        c.drawString(x, y, label)
        c.setFillColor(C_TEXT)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + lw + 3, y, value)

    iy1 = bar_top - 22
    iy2 = bar_top - 38

    info_pair("Name:",  f"{name}  ({age} / {gender})", 28, iy1)
    info_pair("Phone:", phone, 28, iy2)
    info_pair("Date:",  now,   220, iy2)

    return bar_top - bar_h


def _draw_face_placeholder(c, x, y, w, h):
    c.setFillColor(colors.HexColor("#e2e8f0"))
    c.roundRect(x, y, w, h, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(x + w / 2, y + h / 2 - 3,  "No")
    c.drawCentredString(x + w / 2, y + h / 2 - 11, "Photo")


# ══════════════════════════════════════════════════════════════
#  PAGE 2+ GENERATOR using fpdf2
# ══════════════════════════════════════════════════════════════

class AnalysisPDF(FPDF):
    def __init__(self, language, font_path, name, age, gender,
                 report_id, logo_path, total_pages):
        super().__init__()
        self.language    = language
        self.font_path   = font_path
        self.pat_name    = name
        self.pat_age     = str(age)
        self.pat_gender  = gender
        self.report_id   = report_id
        self.logo_path   = logo_path
        self.total_pages = total_pages
        self.page_num    = 2
        self.is_non_latin = language in NON_LATIN_LANGUAGES

        self.font_name = "NotoUni"

        if font_path and os.path.exists(font_path):
            try:
                # ── KEY FIX: fpdf2 requires uni=True removed (it's default in fpdf2)
                # but the font MUST be loaded correctly for Unicode rendering
                self.add_font(self.font_name, style="", fname=font_path)
                print(f"[Font] Loaded: {font_path}")
            except Exception as e:
                print(f"[Font] Failed to load {font_path}: {e}")
                self.font_name = None
        else:
            print(f"[Font] NOT FOUND: {font_path} — falling back to Helvetica")
            self.font_name = None

    def _safe_text(self, text):
        """
        For non-Latin languages: preserve original Unicode text as-is.
        For English/Latin: apply sanitization to handle special chars.
        """
        if not isinstance(text, str):
            text = str(text)
        if self.is_non_latin:
            # Only remove control characters, keep all Unicode
            text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
            return text
        else:
            return sanitize(text)

    def get_font(self, bold=False, size=10):
        if self.font_name:
            self.set_font(self.font_name, size=size)
        else:
            self.set_font("Helvetica", style="B" if bold else "", size=size)

    def draw_header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 22, "F")
        self.set_fill_color(8, 145, 178)
        self.rect(0, 0, 3, 22, "F")

        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, x=5, y=2, w=40, h=18)
            except:
                pass

        self.set_draw_color(51, 65, 85)
        self.line(50, 3, 50, 19)

        self.set_xy(53, 5)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, "AI Detailed Analysis", ln=0)

        self.set_xy(53, 14)
        self.set_text_color(167, 139, 250)
        self.set_font("Helvetica", "", 7)
        self.cell(0, 5, sanitize_structural(f"Language: {self.language}   Observing all 3 dental images"), ln=0)

        self.set_xy(110, 5)
        self.set_text_color(148, 163, 184)
        # Patient name in header — use Noto font if available so it renders correctly
        if self.font_name:
            self.set_font(self.font_name, size=7)
        else:
            self.set_font("Helvetica", "", 7)
        # Patient name: render with safe_text so non-Latin names display correctly
        pat_display = self._safe_text(f"{self.pat_name} ({self.pat_age}/{self.pat_gender})")
        self.cell(95, 5, pat_display, ln=0, align="R")

        self.set_fill_color(124, 58, 237)
        self.rect(0, 22, 210, 1.5, "F")
        self.set_y(25)

    def draw_footer(self):
        self.set_y(-14)
        self.set_fill_color(15, 23, 42)
        self.rect(0, self.get_y(), 210, 14, "F")
        self.set_fill_color(8, 145, 178)
        self.rect(0, self.get_y(), 2.5, 14, "F")

        self.set_xy(5, self.get_y() + 3)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.cell(100, 5,
            sanitize_structural("OralAI  -  AI Oral Health Screening  |  www.oralai.site"), ln=0)

        self.set_x(110)
        self.set_text_color(148, 163, 184)
        self.set_font("Helvetica", "", 7)
        self.cell(0, 5,
            sanitize_structural(f"Report ID: {self.report_id}   |   {datetime.now().strftime('%d %b %Y')}   |   Page {self.page_num} of {self.total_pages}"),
            align="R", ln=0)

    def draw_disclaimer(self):
        y = self.get_y()
        self.set_fill_color(255, 251, 235)
        self.set_draw_color(252, 211, 77)
        self.set_line_width(0.4)
        self.rect(10, y, 190, 8, "FD")
        self.set_xy(12, y + 1.5)
        self.set_text_color(120, 53, 15)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 5,
            sanitize_structural("This is an AI-based screening tool and does not replace a professional dental diagnosis. Please consult a dentist."),
            ln=0)
        self.set_y(y + 9)

    def draw_section_heading(self, text):
        """
        Section headings: use _safe_text so Telugu/Hindi headings render correctly.
        """
        text = self._safe_text(text)
        self.set_fill_color(37, 99, 235)
        self.rect(0, self.get_y(), 210, 8, "F")
        self.set_xy(10, self.get_y() + 1)
        self.set_text_color(255, 255, 255)
        self.get_font(bold=True, size=10)
        self.cell(0, 6, text, ln=1)
        self.ln(3)

    def draw_bullet(self, text):
        """
        Bullet text: use _safe_text to preserve Telugu/other script characters.
        """
        text = self._safe_text(text)
        y = self.get_y()
        self.set_fill_color(37, 99, 235)
        self.ellipse(12, y + 2.5, 2, 2, "F")
        self.set_xy(17, y)
        self.set_text_color(15, 23, 42)
        self.get_font(size=9)
        self.multi_cell(183, 5, text, ln=1)
        self.set_x(10)

    def draw_body_text(self, text):
        """
        Body text: use _safe_text to preserve Telugu/other script characters.
        """
        text = self._safe_text(text)
        self.set_x(10)
        self.set_text_color(15, 23, 42)
        self.get_font(size=9)
        self.multi_cell(190, 5, text, ln=1)

    def _start_new_page_mgmt(self):
        """
        Start a new page during management section rendering.
        Draws a minimal continuation header so the page is not blank.
        """
        self.draw_footer()
        self.page_num += 1
        self.add_page()

        # Slim dark header bar for continuation page
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 14, "F")
        self.set_fill_color(8, 145, 178)
        self.rect(0, 0, 2.5, 14, "F")
        self.set_xy(5, 3)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 10)
        self.cell(130, 8, "Swarnandhra College of Engineering and Technology  -  Management")
        self.set_fill_color(124, 58, 237)
        self.rect(0, 14, 210, 1.5, "F")
        self.set_y(18)

    def draw_management_section(self):
        import json
        try:
            from PIL import Image, ImageDraw
            PIL_AVAILABLE = True
        except ImportError:
            PIL_AVAILABLE = False
            print("[Mgmt] Pillow not installed — circular crop disabled, using square photos")

        config_path = "static/management/config.json"
        if not os.path.exists(config_path):
            print("[Mgmt] config.json not found — skipping management section")
            return

        with open(config_path) as f:
            members = json.load(f)

        if not members:
            return

        # ── Page dimensions ──
        PAGE_H      = 297          # A4 height in mm
        FOOTER_H    = 16           # reserved for footer at bottom
        SAFE_BOTTOM = PAGE_H - FOOTER_H   # = 281 mm — never draw below this

        per_row   = 3
        photo_d   = 28             # circle diameter in mm
        col_w     = 190 / per_row
        # Height one full row occupies: photo + name + title + gap
        ROW_H     = photo_d + 20   # 48 mm per row (generous)
        # Height needed for heading bar + first row
        HEADING_H = 9 + 5          # bar + ln(5)

        # ── Check if we have room for heading + at least one row ──
        space_needed = HEADING_H + ROW_H + 5
        if self.get_y() + space_needed > SAFE_BOTTOM:
            self._start_new_page_mgmt()
        else:
            self.ln(5)

        # ── Section heading bar ──
        self.set_fill_color(15, 23, 42)
        self.rect(0, self.get_y(), 210, 9, "F")
        self.set_fill_color(8, 145, 178)
        self.rect(0, self.get_y(), 2.5, 9, "F")
        self.set_xy(10, self.get_y() + 1.5)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 6, "Swarnandhra College of Engineering and Technology  -  Management", ln=1)
        self.ln(5)

        def make_circle_img(src_path):
            """Crops image to circle, returns temp PNG path."""
            try:
                img = Image.open(src_path).convert("RGBA")
                size = min(img.size)
                left = (img.width  - size) // 2
                top  = (img.height - size) // 2
                img  = img.crop((left, top, left + size, top + size))
                img  = img.resize((220, 220), Image.LANCZOS)

                mask = Image.new("L", (220, 220), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, 220, 220), fill=255)

                result = Image.new("RGBA", (220, 220), (255, 255, 255, 0))
                result.paste(img, (0, 0), mask)

                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                result.save(tmp.name, "PNG")
                return tmp.name
            except Exception as e:
                print(f"[Mgmt] Circle crop failed: {e}")
                return None

        temp_files = []

        for row_start in range(0, len(members), per_row):
            row_members = members[row_start : row_start + per_row]

            # ── KEY FIX: check space before drawing each row ──
            # If this row won't fit, start a new continuation page
            if self.get_y() + ROW_H > SAFE_BOTTOM:
                self._start_new_page_mgmt()

            row_y = self.get_y()

            for i, member in enumerate(row_members):
                cx = 10 + i * col_w + col_w / 2
                px = cx - photo_d / 2
                py = row_y

                img_path = os.path.join("static", "management", member.get("file", ""))

                # Blue circle border
                self.set_draw_color(37, 99, 235)
                self.set_line_width(0.7)
                self.ellipse(px - 1, py - 1, photo_d + 2, photo_d + 2, "D")

                if os.path.exists(img_path):
                    if PIL_AVAILABLE:
                        circle_path = make_circle_img(img_path)
                    else:
                        circle_path = None

                    if circle_path:
                        temp_files.append(circle_path)
                        try:
                            self.image(circle_path, x=px, y=py, w=photo_d, h=photo_d)
                        except Exception as e:
                            print(f"[Mgmt] Image draw error: {e}")
                    else:
                        try:
                            self.image(img_path, x=px, y=py, w=photo_d, h=photo_d)
                        except Exception as e:
                            print(f"[Mgmt] Fallback image draw error: {e}")
                else:
                    # Grey placeholder circle
                    self.set_fill_color(226, 232, 240)
                    self.ellipse(px, py, photo_d, photo_d, "F")
                    self.set_xy(px, py + photo_d / 2 - 2)
                    self.set_text_color(148, 163, 184)
                    self.set_font("Helvetica", "", 6)
                    self.cell(photo_d, 4, "No Photo", align="C", ln=0)

                # Name
                self.set_xy(10 + i * col_w, py + photo_d + 2)
                self.set_text_color(15, 23, 42)
                self.set_font("Helvetica", "B", 8)
                self.cell(col_w, 4.5,
                          sanitize_structural(member.get("name", "")),
                          align="C", ln=0)

                # Title
                self.set_xy(10 + i * col_w, py + photo_d + 7)
                self.set_text_color(100, 116, 139)
                self.set_font("Helvetica", "", 6.5)
                self.multi_cell(col_w, 3.5,
                                sanitize_structural(member.get("title", "")),
                                align="C")

            # Move Y past this row
            self.set_y(row_y + ROW_H)

        # ── Clean up temp circle PNGs ──
        for tmp in temp_files:
            try:
                os.remove(tmp)
            except:
                pass

    def header(self):
        pass

    def footer(self):
        pass


def generate_analysis_pages_fpdf2(claude_analysis, language, name, age, gender,
                                   report_id, logo_path, start_page, total_pages):
    font_file = LANG_FONT_MAP.get(language, "NotoSans-Regular.ttf")
    font_path = os.path.join(FONTS_DIR, font_file)

    if not os.path.exists(font_path):
        print(f"[Font] WARNING: {font_path} not found!")
        print(f"[Font] Download NotoSans fonts from: https://fonts.google.com/noto")
        print(f"[Font] Place the .ttf file in: {FONTS_DIR}/")

    pdf = AnalysisPDF(
        language=language,
        font_path=font_path,
        name=name, age=age, gender=gender,
        report_id=report_id,
        logo_path=logo_path,
        total_pages=total_pages
    )
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.draw_header()

    # ── KEY FIX: pass language to clean_markdown so non-Latin text is preserved ──
    cleaned   = clean_markdown(claude_analysis, language=language)
    lines_raw = cleaned.split("\n")

    BOTTOM_LIMIT = 252

    render_items = []
    for raw_line in lines_raw:
        line = raw_line.strip()
        if not line:
            render_items.append(("blank", ""))
            continue
        if re.match(r'^\d+\.\s+[^\s]', line) and len(line) < 80:
            render_items.append(("heading", line))
        elif line.startswith("- ") or line.startswith("• ") or line.startswith("* "):
            render_items.append(("bullet", line[2:].strip()))
        else:
            render_items.append(("text", line))

    for item_type, item_text in render_items:

        if pdf.get_y() > BOTTOM_LIMIT:
            pdf.draw_footer()
            pdf.page_num += 1
            pdf.add_page()
            pdf.set_fill_color(15, 23, 42)
            pdf.rect(0, 0, 210, 14, "F")
            pdf.set_fill_color(8, 145, 178)
            pdf.rect(0, 0, 2.5, 14, "F")
            pdf.set_xy(5, 3)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(130, 8, sanitize_structural("AI Detailed Analysis (continued)"))
            pdf.set_text_color(148, 163, 184)
            if pdf.font_name:
                pdf.set_font(pdf.font_name, size=7)
            else:
                pdf.set_font("Helvetica", "", 7)
            # Patient name in continuation header
            cont_name = pdf._safe_text(f"{name} ({age}/{gender})")
            pdf.cell(65, 8, cont_name, align="R")
            pdf.set_fill_color(124, 58, 237)
            pdf.rect(0, 14, 210, 1.5, "F")
            pdf.set_y(18)

        if item_type == "blank":
            pdf.ln(3)
        elif item_type == "heading":
            pdf.ln(4)
            pdf.draw_section_heading(item_text)
            pdf.ln(2)
        elif item_type == "bullet":
            pdf.draw_bullet(item_text)
        else:
            if item_text:
                pdf.draw_body_text(item_text)
                pdf.ln(1)

    # ── Disclaimer then Management photos ──
    pdf.draw_disclaimer()
    pdf.draw_management_section()
    pdf.draw_footer()

    temp_path = f"static/reports/temp_analysis_{report_id}.pdf"
    pdf.output(temp_path)
    return temp_path, pdf.page_num


def _build_page1(c, W, H, header_h, name, age, gender, phone, now,
                 logo_path, face_photo_path, img_parts, img_w, img_h,
                 card_h, gap, pill_colors, detected_labels,
                 recommendations, no_issues, report_id, total_pages):
    """
    Draw all page-1 content onto canvas `c`.
    Extracted to avoid duplicating the massive page-1 drawing block.
    """
    # Header
    c.setFillColor(C_HEADER)
    c.rect(0, H - header_h, W, header_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.rect(0, H - header_h, 8, header_h, fill=1, stroke=0)

    if os.path.exists(logo_path):
        logo_y = H - header_h + (header_h - 60) / 2
        c.drawImage(logo_path, 20, logo_y,
                    width=180, height=60,
                    preserveAspectRatio=True, mask="auto")
        c.setStrokeColor(colors.HexColor("#334155"))
        c.setLineWidth(1)
        c.line(210, H - header_h + 14, 210, H - 14)
        c.setFillColor(C_WHITE)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(222, H - header_h + 44, "Oral Health Screening Report")
        c.setFillColor(colors.HexColor("#7dd3fc"))
        c.setFont("Helvetica", 9)
        c.drawString(224, H - header_h + 26, "powered by OralAI")
    else:
        c.setFillColor(C_WHITE)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(30, H - header_h + 44, "Oral Health Screening Report")

    bar_bottom = draw_patient_info_bar(
        c, W, H, header_h,
        name, age, gender, phone, now,
        face_photo_path=face_photo_path
    )

    cur_y = bar_bottom
    cur_y = draw_section_bar_rl(c, W, cur_y, "  AI SCREENING REPORT")

    card_y = cur_y - 14 - card_h

    for i, (lbl, fname) in enumerate(img_parts):
        ix  = 28 + gap + i * (img_w + gap)
        iy2 = card_y

        c.setFillColor(colors.HexColor("#cbd5e1"))
        c.roundRect(ix + 3, iy2 - 3, img_w, card_h, 10, fill=1, stroke=0)
        c.setFillColor(C_WHITE)
        c.roundRect(ix, iy2, img_w, card_h, 10, fill=1, stroke=0)
        c.setFillColor(C_SURFACE2)
        c.roundRect(ix + 5, iy2 + 28, img_w - 10, img_h, 8, fill=1, stroke=0)

        img_path = os.path.join("static", "results", fname)
        if os.path.exists(img_path):
            c.drawImage(img_path, ix + 5, iy2 + 28,
                        width=img_w - 10, height=img_h,
                        preserveAspectRatio=True, mask="auto")

        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.8)
        c.roundRect(ix, iy2, img_w, card_h, 10, fill=0, stroke=1)
        c.setFillColor(pill_colors[i])
        c.roundRect(ix + 14, iy2 + 7, img_w - 28, 17, 8, fill=1, stroke=0)
        c.setFillColor(C_WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(ix + img_w / 2, iy2 + 12, lbl)

    cur_y = card_y - 18

    # ── Legend ──
    detected = [k for k in ["malaligned", "stains", "caries", "pit_fissure"]
                if k in detected_labels]
    if detected:
        c.setFillColor(C_SURFACE2)
        c.roundRect(28, cur_y - 10, W - 56, 22, 6, fill=1, stroke=0)
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.6)
        c.roundRect(28, cur_y - 10, W - 56, 22, 6, fill=0, stroke=1)
        lx = 44
        for key in detected:
            col  = COND_COLOR[key]
            text = COND_LABEL[key]
            c.setFillColor(col)
            c.circle(lx + 5, cur_y + 2, 5, fill=1, stroke=0)
            c.setFillColor(C_TEXT)
            c.setFont("Helvetica", 9)
            c.drawString(lx + 14, cur_y - 2, text)
            lx += c.stringWidth(text, "Helvetica", 9) + 34
        cur_y -= 24

    # ── Treatment Recommendations ──
    cur_y -= 4
    cur_y = draw_section_bar_rl(c, W, cur_y, "  TREATMENT RECOMMENDATIONS")
    cur_y -= 8

    if no_issues:
        rec_text = recommendations[0]["recommendation"] if recommendations else "No issues detected."
        lines    = wrap_text(rec_text, 76)
        row_h    = max(52, 22 + len(lines) * 14)
        cur_y   -= row_h + 4

        c.setFillColor(C_SUCCESS_BG)
        c.roundRect(28, cur_y, W - 56, row_h, 8, fill=1, stroke=0)
        c.setStrokeColor(C_SUCCESS_BD)
        c.setLineWidth(1)
        c.roundRect(28, cur_y, W - 56, row_h, 8, fill=0, stroke=1)
        c.setFillColor(C_SUCCESS)
        c.rect(28, cur_y, 5, row_h, fill=1, stroke=0)
        c.setFillColor(C_SUCCESS)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(42, cur_y + row_h - 15, "No major oral health issues detected")
        ty = cur_y + row_h - 29
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 9.5)
        for ln in lines:
            c.drawString(42, ty, ln)
            ty -= 13

    else:
        for rec in recommendations:
            if rec["label"] == "none":
                continue
            label     = rec["label"]
            conf      = rec.get("confidence", 0)
            rec_text  = rec["recommendation"]
            lines     = wrap_text(rec_text, 73)
            row_h     = max(56, 30 + len(lines) * 13)
            col       = COND_COLOR.get(label, C_MUTED)
            bg        = COND_BG.get(label, C_SURFACE)
            bd        = COND_BD.get(label, C_BORDER)
            label_txt = COND_LABEL.get(label, label.title())

            cur_y -= row_h + 8
            c.setFillColor(bg)
            c.roundRect(28, cur_y, W - 56, row_h, 8, fill=1, stroke=0)
            c.setStrokeColor(bd)
            c.setLineWidth(1)
            c.roundRect(28, cur_y, W - 56, row_h, 8, fill=0, stroke=1)
            c.setFillColor(col)
            c.rect(28, cur_y, 6, row_h, fill=1, stroke=0)
            c.setFillColor(col)
            c.circle(52, cur_y + row_h - 18, 8, fill=1, stroke=0)
            c.setFillColor(C_TEXT)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(68, cur_y + row_h - 14, label_txt)
            bx = 68 + c.stringWidth(label_txt, "Helvetica-Bold", 12) + 8
            c.setFillColor(col)
            c.roundRect(bx, cur_y + row_h - 19, 56, 14, 5, fill=1, stroke=0)
            c.setFillColor(C_WHITE)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawCentredString(bx + 28, cur_y + row_h - 12, f"{conf:.0%} confidence")
            c.setFillColor(C_TEXT)
            c.setFont("Helvetica", 9.5)
            ty = cur_y + row_h - 30
            for ln in lines:
                c.drawString(68, ty, ln)
                ty -= 13

    draw_footer_rl(c, W, report_id, 1, total_pages)
    c.save()


def generate_pdf(user_data, detected_labels, report_id,
                 recommendations=None, claude_analysis=None, screening_id=None):

    name     = user_data.get("name", "Patient")
    age      = user_data.get("age", "N/A")
    gender   = user_data.get("gender", "N/A")
    phone    = user_data.get("phone", "N/A")
    language = user_data.get("language", "English")
    now      = datetime.now().strftime("%d %b %Y  %I:%M %p")

    if recommendations is None:
        recommendations = []

    report_path = f"static/reports/{report_id}.pdf"
    logo_path   = "static/logo.png"

    face_photo_path = get_face_photo_path(screening_id, report_id)

    img_h    = 152
    img_w    = 152
    gap      = (595.27 - 56 - img_w * 3) / 4   # A4 width approx
    card_h   = img_h + 34
    pill_colors = [C_ACCENT, C_TEAL, C_PURPLE]

    if screening_id:
        img_parts = [
            ("Upper Teeth", f"{screening_id}_upper_yolo.jpg"),
            ("Front Teeth", f"{screening_id}_front_yolo.jpg"),
            ("Lower Teeth", f"{screening_id}_lower_yolo.jpg"),
        ]
    else:
        img_parts = [
            ("Upper Teeth", "upper_yolo.jpg"),
            ("Front Teeth", "front_yolo.jpg"),
            ("Lower Teeth", "lower_yolo.jpg"),
        ]

    no_issues = (not recommendations or
                 (len(recommendations) == 1 and recommendations[0]["label"] == "none"))

    # ── Draw page 1 with placeholder total (will redraw after merge) ──
    c = rl_canvas.Canvas(report_path, pagesize=A4)
    W, H = A4
    header_h = 90

    _build_page1(
        c, W, H, header_h, name, age, gender, phone, now,
        logo_path, face_photo_path, img_parts,
        img_w, img_h, card_h, gap, pill_colors,
        detected_labels, recommendations, no_issues,
        report_id, total_pages=99  # placeholder — will be corrected below
    )

    # ── Pages 2+ using fpdf2 ──
    if claude_analysis:
        try:
            temp_path, last_fpdf_page = generate_analysis_pages_fpdf2(
                claude_analysis=claude_analysis,
                language=language,
                name=name, age=age, gender=gender,
                report_id=report_id,
                logo_path=logo_path,
                start_page=2,
                total_pages=99   # placeholder — corrected after merge
            )

            from pypdf import PdfWriter, PdfReader

            # ── First merge to count actual pages ──
            writer = PdfWriter()
            for page in PdfReader(report_path).pages:
                writer.add_page(page)
            for page in PdfReader(temp_path).pages:
                writer.add_page(page)

            actual_pages = len(writer.pages)
            print(f"[PDF] Total pages: {actual_pages}, language={language}")

            # ── Redraw page 1 with correct total_pages ──
            c2 = rl_canvas.Canvas(report_path, pagesize=A4)
            _build_page1(
                c2, W, H, header_h, name, age, gender, phone, now,
                logo_path, face_photo_path, img_parts,
                img_w, img_h, card_h, gap, pill_colors,
                detected_labels, recommendations, no_issues,
                report_id, total_pages=actual_pages
            )

            # ── Regenerate analysis pages with correct total_pages ──
            os.remove(temp_path)
            temp_path2, _ = generate_analysis_pages_fpdf2(
                claude_analysis=claude_analysis,
                language=language,
                name=name, age=age, gender=gender,
                report_id=report_id,
                logo_path=logo_path,
                start_page=2,
                total_pages=actual_pages   # ← correct total now
            )

            # ── Final merge ──
            writer2 = PdfWriter()
            for page in PdfReader(report_path).pages:
                writer2.add_page(page)
            for page in PdfReader(temp_path2).pages:
                writer2.add_page(page)

            with open(report_path, "wb") as f:
                writer2.write(f)

            os.remove(temp_path2)
            print(f"[PDF] Final report saved: {report_path}")

        except Exception as e:
            print(f"Analysis page merge failed: {e}")
            import traceback
            traceback.print_exc()
            print("Page 1 only saved.")

    return report_path