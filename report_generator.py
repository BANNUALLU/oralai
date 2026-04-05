from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from fpdf import FPDF
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import os
import re
import base64
import tempfile
import traceback

# ── Safe pypdf import with fallback ─────────────────────────
try:
    from pypdf import PdfWriter, PdfReader
    print("[PDF] Using pypdf")
except ImportError:
    try:
        from PyPDF2 import PdfWriter, PdfReader
        print("[PDF] Using PyPDF2 (fallback)")
    except ImportError:
        PdfWriter = None
        PdfReader = None
        print("[PDF] WARNING: Neither pypdf nor PyPDF2 found!")


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

NON_LATIN_LANGUAGES = {
    "Hindi", "Marathi", "Telugu", "Tamil",
    "Kannada", "Malayalam", "Bengali", "Arabic"
}

# ── Font sizes — kept small so more fits per page ─────────────
LANG_FONT_SIZE = {
    "Telugu":    7.0,
    "Hindi":     7.5,
    "Marathi":   7.5,
    "Tamil":     7.0,
    "Kannada":   7.0,
    "Malayalam": 7.0,
    "Bengali":   7.5,
    "Arabic":    7.5,
    "English":   9.0,
}

# ── Page layout constants ──────────────────────────────────────
PAGE_H_MM       = 297
FOOTER_H_MM     = 14
SAFE_BOTTOM_LATIN     = PAGE_H_MM - FOOTER_H_MM - 6
SAFE_BOTTOM_NON_LATIN = PAGE_H_MM - FOOTER_H_MM - 20
CONTENT_TOP_MM  = 18
DISCLAIMER_H_MM = 10


def sanitize(text):
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


# ══════════════════════════════════════════════════════════════
#  PAGE 1 FOOTER  (dark navy, 3-section layout)
# ══════════════════════════════════════════════════════════════

def draw_footer_rl(c, W, report_id, page_num, total_pages):
    footer_h = 22

    # Dark navy background
    c.setFillColor(C_HEADER)
    c.rect(0, 0, W, footer_h, fill=1, stroke=0)

    # Thin accent line on top
    c.setStrokeColor(C_ACCENT)
    c.setLineWidth(1)
    c.line(0, footer_h, W, footer_h)

    mid_y = 7  # vertical text baseline

    # ── Left: Branding ──────────────────────────────────────
    c.setFillColor(C_WHITE)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(14, mid_y, "OralAI  -  AI Oral Health Screening")
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(14 + 178, mid_y, "|  www.oralai.site")

    # ── Center: Report ID ───────────────────────────────────
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(W / 2, mid_y, f"Report ID: {report_id}")

    # ── Right: Date | Page ──────────────────────────────────
    c.setFillColor(C_WHITE)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(W - 14, mid_y,
        f"{datetime.now().strftime('%d %b %Y')}   |   Page {page_num} of {total_pages}")


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
            return path
        path = os.path.join("static", "results", f"{screening_id}_face.jpg")
        if os.path.exists(path):
            return path
    path = os.path.join("static", "results", f"{report_id}_face.jpg")
    if os.path.exists(path):
        return path
    return None


# ══════════════════════════════════════════════════════════════
#  PATIENT INFO BAR  (bigger photo, Name bold, Phone+Date row)
# ══════════════════════════════════════════════════════════════

def draw_patient_info_bar(c, W, H, header_h, name, age, gender, phone, now, face_photo_path=None):
    bar_top = H - header_h
    bar_h   = 60
    c.setFillColor(C_SURFACE2)
    c.rect(0, bar_top - bar_h, W, bar_h, fill=1, stroke=0)
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.8)
    c.line(0, bar_top - bar_h, W, bar_top - bar_h)

    # ── Face photo ─────────────────────────────────────────
    photo_w, photo_h = 52, 54
    photo_x = W - photo_w - 14
    photo_y = bar_top - bar_h + 3

    if face_photo_path and os.path.exists(face_photo_path):
        c.setStrokeColor(C_ACCENT)
        c.setLineWidth(1.5)
        c.roundRect(photo_x - 2, photo_y - 2, photo_w + 4, photo_h + 4, 5, fill=0, stroke=1)
        try:
            c.drawImage(face_photo_path, photo_x, photo_y,
                        width=photo_w, height=photo_h,
                        preserveAspectRatio=True, mask="auto")
        except Exception as e:
            print(f"[Page1] Face photo error: {e}")
            _draw_face_placeholder(c, photo_x, photo_y, photo_w, photo_h)
    else:
        _draw_face_placeholder(c, photo_x, photo_y, photo_w, photo_h)

    # ── Text content ───────────────────────────────────────
    text_x = 20

    # NAME label
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(text_x, bar_top - 16, "NAME")

    # Name bold + age/gender inline
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(text_x, bar_top - 28, f"{name}")
    name_w = c.stringWidth(f"{name}", "Helvetica-Bold", 12)
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 9)
    c.drawString(text_x + name_w + 8, bar_top - 26, f"{age} yrs  •  {gender}")

    # PHONE label + value
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(text_x, bar_top - 44, "PHONE")
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(text_x, bar_top - 54, f"{phone}")

    # DATE — right-aligned before photo
    date_x = photo_x - 20
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawRightString(date_x, bar_top - 44, "DATE")
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(date_x, bar_top - 54, now)

    return bar_top - bar_h


def _draw_face_placeholder(c, x, y, w, h):
    c.setFillColor(colors.HexColor("#e2e8f0"))
    c.roundRect(x, y, w, h, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(x + w / 2, y + h / 2 - 3,  "No")
    c.drawCentredString(x + w / 2, y + h / 2 - 11, "Photo")


# ══════════════════════════════════════════════════════════════
#  PILLOW HELPERS
# ══════════════════════════════════════════════════════════════

def render_text_to_image(text, font_path, font_size_pt=9,
                          text_color=(15, 23, 42), bg_color=None,
                          max_width_mm=183, dpi=200):
    try:
        px_per_mm = dpi / 25.4
        max_w_px  = int(max_width_mm * px_per_mm)
        font_px   = max(int(font_size_pt * dpi / 72), 10)
        pil_font  = ImageFont.truetype(font_path, font_px)

        words, lines, current = text.split(), [], ""
        dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        for word in words:
            test = (current + " " + word).strip() if current else word
            if dummy.textlength(test, font=pil_font) <= max_w_px:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            return None

        line_heights = []
        for ln in lines:
            bbox = dummy.textbbox((0, 0), ln, font=pil_font)
            line_heights.append(bbox[3] - bbox[1])

        line_gap = max(int(font_px * 0.28), 3)
        total_h  = sum(line_heights) + line_gap * (len(lines) - 1) + int(font_px * 0.3)
        total_h  = max(total_h, font_px + 4)

        bg  = bg_color if bg_color else (255, 255, 255)
        img = Image.new("RGB", (max_w_px, total_h), bg)
        draw = ImageDraw.Draw(img)
        y = int(font_px * 0.05)
        for i, ln in enumerate(lines):
            draw.text((0, y), ln, font=pil_font, fill=text_color)
            y += line_heights[i] + line_gap

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name, "PNG")
        tmp.close()
        return tmp.name, total_h / px_per_mm, max_w_px / px_per_mm
    except Exception as e:
        print(f"[TextImg] render failed: {e}")
        return None


def measure_text_height_mm(text, font_path, font_size_pt=9,
                            max_width_mm=183, dpi=200):
    """Measure rendered height WITHOUT writing a file."""
    try:
        px_per_mm = dpi / 25.4
        max_w_px  = int(max_width_mm * px_per_mm)
        font_px   = max(int(font_size_pt * dpi / 72), 10)
        pil_font  = ImageFont.truetype(font_path, font_px)

        words, lines, current = text.split(), [], ""
        dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        for word in words:
            test = (current + " " + word).strip() if current else word
            if dummy.textlength(test, font=pil_font) <= max_w_px:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            return None

        line_heights = []
        for ln in lines:
            bbox = dummy.textbbox((0, 0), ln, font=pil_font)
            line_heights.append(bbox[3] - bbox[1])

        line_gap = max(int(font_px * 0.28), 3)
        total_h  = sum(line_heights) + line_gap * (len(lines) - 1) + int(font_px * 0.3)
        return max(total_h, font_px + 4) / px_per_mm
    except Exception as e:
        print(f"[Measure] failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════
#  AnalysisPDF class
# ══════════════════════════════════════════════════════════════

class AnalysisPDF(FPDF):
    def __init__(self, language, font_path, name, age, gender,
                 report_id, logo_path, total_pages):
        super().__init__()
        self.language     = language
        self.font_path    = font_path
        self.pat_name     = name
        self.pat_age      = str(age)
        self.pat_gender   = gender
        self.report_id    = report_id
        self.logo_path    = logo_path
        self.total_pages  = total_pages
        self.page_num     = 2
        self.is_non_latin = language in NON_LATIN_LANGUAGES
        self._tmp_images  = []
        self.body_font_pt = LANG_FONT_SIZE.get(language, 9.0)

        self.safe_bottom = (SAFE_BOTTOM_NON_LATIN if self.is_non_latin
                            else SAFE_BOTTOM_LATIN)

        self.font_name = "NotoUni"
        if font_path and os.path.exists(font_path):
            try:
                self.add_font(self.font_name, style="", fname=font_path)
                print(f"[Font] Loaded {font_path} @ {self.body_font_pt}pt")
            except Exception as e:
                print(f"[Font] Failed: {e}")
                self.font_name = None
        else:
            print(f"[Font] NOT FOUND: {font_path}")
            self.font_name = None

    def cleanup_tmp(self):
        for p in self._tmp_images:
            try:
                os.remove(p)
            except:
                pass
        self._tmp_images = []

    def _safe_text(self, text):
        if not isinstance(text, str):
            text = str(text)
        if self.is_non_latin:
            return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return sanitize(text)

    def get_font(self, bold=False, size=None):
        sz = size if size is not None else self.body_font_pt
        if self.font_name:
            self.set_font(self.font_name, size=sz)
        else:
            self.set_font("Helvetica", style="B" if bold else "", size=sz)

    # ── Page break helpers ────────────────────────────────────
    def _draw_continuation_header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 14, "F")
        self.set_fill_color(8, 145, 178)
        self.rect(0, 0, 2.5, 14, "F")
        self.set_xy(5, 3)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.cell(130, 8, sanitize("AI Detailed Analysis (continued)"))
        self.set_fill_color(124, 58, 237)
        self.rect(0, 14, 210, 1.5, "F")
        self.set_y(CONTENT_TOP_MM)

    def _new_page(self):
        self.draw_footer()
        self.page_num += 1
        self.add_page()
        self._draw_continuation_header()

    def _ensure_space(self, needed_mm):
        if self.get_y() + needed_mm > self.safe_bottom:
            self._new_page()

    def _measure_h(self, text, max_width_mm=183):
        if not self.font_path or not os.path.exists(self.font_path):
            return None
        return measure_text_height_mm(
            text, self.font_path,
            font_size_pt=self.body_font_pt,
            max_width_mm=max_width_mm,
            dpi=200
        )

    def _embed_text_image(self, text, text_color=(15, 23, 42),
                          bg_color=None, x_mm=10, max_width_mm=183):
        if not self.font_path or not os.path.exists(self.font_path):
            return 0

        h_preview = self._measure_h(text, max_width_mm=max_width_mm)
        if h_preview is not None:
            h_with_margin = h_preview * 1.15 + 2.0
        else:
            h_with_margin = 15

        if self.get_y() + h_with_margin > self.safe_bottom:
            self._new_page()

        result = render_text_to_image(
            text, self.font_path,
            font_size_pt=self.body_font_pt,
            text_color=text_color,
            bg_color=bg_color if bg_color else (255, 255, 255),
            max_width_mm=max_width_mm,
            dpi=200
        )
        if result is None:
            return 0

        tmp_path, h_mm, w_mm = result
        self._tmp_images.append(tmp_path)

        if self.get_y() + h_mm > self.safe_bottom:
            self._new_page()

        self.image(tmp_path, x=x_mm, y=self.get_y(), w=max_width_mm, h=h_mm)
        self.set_y(self.get_y() + h_mm + 1.0)
        return h_mm

    # ── Header / Footer / Disclaimer ─────────────────────────
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
        self.cell(0, 5, sanitize(f"Language: {self.language}   Observing all 3 dental images"), ln=0)
        self.set_xy(110, 5)
        self.set_text_color(148, 163, 184)
        self.set_font("Helvetica", "", 7)
        pat_display = f"{self.pat_name} ({self.pat_age}/{self.pat_gender})"
        self.cell(95, 5, pat_display if not self.is_non_latin else "(see report)", ln=0, align="R")
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
        self.cell(100, 5, sanitize("OralAI  -  AI Oral Health Screening  |  www.oralai.site"), ln=0)
        self.set_x(110)
        self.set_text_color(148, 163, 184)
        self.set_font("Helvetica", "", 7)
        self.cell(0, 5,
            sanitize(f"Report ID: {self.report_id}   |   {datetime.now().strftime('%d %b %Y')}   |   Page {self.page_num} of {self.total_pages}"),
            align="R", ln=0)

    def draw_disclaimer(self):
        self._ensure_space(DISCLAIMER_H_MM + 4)
        y = self.get_y()
        self.set_fill_color(255, 251, 235)
        self.set_draw_color(252, 211, 77)
        self.set_line_width(0.4)
        self.rect(10, y, 190, 8, "FD")
        self.set_xy(12, y + 1.5)
        self.set_text_color(120, 53, 15)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 5, sanitize(
            "This is an AI-based screening tool and does not replace a professional dental diagnosis. Please consult a dentist."),
            ln=0)
        self.set_y(y + 9)

    # ── Section heading ───────────────────────────────────────
    def draw_section_heading(self, text):
        text = self._safe_text(text)
        self._ensure_space(25)
        bar_y = self.get_y()
        self.set_fill_color(37, 99, 235)
        self.rect(0, bar_y, 210, 9, "F")

        if self.is_non_latin and self.font_path and os.path.exists(self.font_path):
            result = render_text_to_image(
                text, self.font_path,
                font_size_pt=self.body_font_pt,
                text_color=(255, 255, 255),
                bg_color=(37, 99, 235),
                max_width_mm=190, dpi=200
            )
            if result:
                tmp_path, h_mm, w_mm = result
                self._tmp_images.append(tmp_path)
                img_y = bar_y + max(0, (9 - h_mm) / 2)
                self.image(tmp_path, x=10, y=img_y, w=190, h=min(h_mm, 9))
                self.set_y(bar_y + 9)
                self.ln(2)
                return

        self.set_xy(10, bar_y + 1.5)
        self.set_text_color(255, 255, 255)
        self.get_font(bold=True, size=self.body_font_pt + 0.5)
        self.cell(0, 6, text, ln=1)
        self.ln(2)

    # ── Bullet ────────────────────────────────────────────────
    def draw_bullet(self, text):
        text = self._safe_text(text)

        if self.is_non_latin and self.font_path and os.path.exists(self.font_path):
            h_preview = self._measure_h(text, max_width_mm=176)
            needed = (h_preview * 1.15 + 3.0) if h_preview is not None else 14

            if self.get_y() + needed > self.safe_bottom:
                self._new_page()

            y_start = self.get_y()
            self.set_fill_color(37, 99, 235)
            self.ellipse(12, y_start + 2.5, 2, 2, "F")
            self._embed_text_image(text, text_color=(15, 23, 42), x_mm=17, max_width_mm=176)
            self.set_x(10)
            return

        lines_est = max(1, len(text) // 76 + 1)
        self._ensure_space(lines_est * 4.5 + 2)
        y = self.get_y()
        self.set_fill_color(37, 99, 235)
        self.ellipse(12, y + 2.5, 2, 2, "F")
        self.set_xy(17, y)
        self.set_text_color(15, 23, 42)
        self.get_font(size=self.body_font_pt)
        self.multi_cell(183, 4.5, text, ln=1)
        self.set_x(10)

    # ── Body text ─────────────────────────────────────────────
    def draw_body_text(self, text):
        text = self._safe_text(text)

        if self.is_non_latin and self.font_path and os.path.exists(self.font_path):
            self._embed_text_image(text, text_color=(15, 23, 42), x_mm=10, max_width_mm=183)
            return

        lines_est = max(1, len(text) // 82 + 1)
        self._ensure_space(lines_est * 4.5 + 2)
        self.set_x(10)
        self.set_text_color(15, 23, 42)
        self.get_font(size=self.body_font_pt)
        self.multi_cell(190, 4.5, text, ln=1)

    # ── Management section ────────────────────────────────────
    def _start_new_page_mgmt(self):
        self.draw_footer()
        self.page_num += 1
        self.add_page()
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
            from PIL import Image as PilImage, ImageDraw as PilDraw
            PIL_AVAILABLE = True
        except ImportError:
            PIL_AVAILABLE = False

        config_path = "static/management/config.json"
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path) as f:
                members = json.load(f)
        except Exception as e:
            print(f"[Mgmt] Could not load config.json: {e}")
            return
        if not members:
            return

        PAGE_H      = 297
        FOOTER_H    = 16
        SAFE_BOTTOM = PAGE_H - FOOTER_H
        per_row     = 3
        photo_d     = 28
        col_w       = 190 / per_row
        ROW_H       = photo_d + 20
        HEADING_H   = 9 + 5

        space_needed = HEADING_H + ROW_H + 5
        if self.get_y() + space_needed > SAFE_BOTTOM:
            self._start_new_page_mgmt()
        else:
            self.ln(5)

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
            try:
                img  = PilImage.open(src_path).convert("RGBA")
                size = min(img.size)
                left = (img.width  - size) // 2
                top  = (img.height - size) // 2
                img  = img.crop((left, top, left + size, top + size))
                img  = img.resize((220, 220), PilImage.LANCZOS)
                mask = PilImage.new("L", (220, 220), 0)
                draw = PilDraw.Draw(mask)
                draw.ellipse((0, 0, 220, 220), fill=255)
                result = PilImage.new("RGBA", (220, 220), (255, 255, 255, 0))
                result.paste(img, (0, 0), mask)
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                result.save(tmp.name, "PNG")
                return tmp.name
            except Exception as e:
                print(f"[Mgmt] Circle crop failed: {e}")
                return None

        temp_files = []
        for row_start in range(0, len(members), per_row):
            row_members = members[row_start: row_start + per_row]
            if self.get_y() + ROW_H > SAFE_BOTTOM:
                self._start_new_page_mgmt()
            row_y = self.get_y()
            for i, member in enumerate(row_members):
                cx = 10 + i * col_w + col_w / 2
                px = cx - photo_d / 2
                py = row_y
                img_path = os.path.join("static", "management", member.get("file", ""))
                self.set_draw_color(37, 99, 235)
                self.set_line_width(0.7)
                self.ellipse(px - 1, py - 1, photo_d + 2, photo_d + 2, "D")
                if os.path.exists(img_path):
                    circle_path = make_circle_img(img_path) if PIL_AVAILABLE else None
                    if circle_path:
                        temp_files.append(circle_path)
                        try:
                            self.image(circle_path, x=px, y=py, w=photo_d, h=photo_d)
                        except Exception as e:
                            print(f"[Mgmt] Image error: {e}")
                    else:
                        try:
                            self.image(img_path, x=px, y=py, w=photo_d, h=photo_d)
                        except Exception as e:
                            print(f"[Mgmt] Fallback error: {e}")
                else:
                    self.set_fill_color(226, 232, 240)
                    self.ellipse(px, py, photo_d, photo_d, "F")
                    self.set_xy(px, py + photo_d / 2 - 2)
                    self.set_text_color(148, 163, 184)
                    self.set_font("Helvetica", "", 6)
                    self.cell(photo_d, 4, "No Photo", align="C", ln=0)
                self.set_xy(10 + i * col_w, py + photo_d + 2)
                self.set_text_color(15, 23, 42)
                self.set_font("Helvetica", "B", 8)
                self.cell(col_w, 4.5, sanitize(member.get("name", "")), align="C", ln=0)
                self.set_xy(10 + i * col_w, py + photo_d + 7)
                self.set_text_color(100, 116, 139)
                self.set_font("Helvetica", "", 6.5)
                self.multi_cell(col_w, 3.5, sanitize(member.get("title", "")), align="C")
            self.set_y(row_y + ROW_H)

        for tmp in temp_files:
            try:
                os.remove(tmp)
            except:
                pass

    def header(self):
        pass

    def footer(self):
        pass


# ══════════════════════════════════════════════════════════════
#  generate_analysis_pages_fpdf2
# ══════════════════════════════════════════════════════════════

def generate_analysis_pages_fpdf2(claude_analysis, language, name, age, gender,
                                   report_id, logo_path, start_page, total_pages):
    font_file = LANG_FONT_MAP.get(language, "NotoSans-Regular.ttf")
    font_path = os.path.join(FONTS_DIR, font_file)
    if not os.path.exists(font_path):
        print(f"[Font] WARNING: {font_path} not found — Helvetica fallback")

    pdf = AnalysisPDF(
        language=language, font_path=font_path,
        name=name, age=age, gender=gender,
        report_id=report_id, logo_path=logo_path,
        total_pages=total_pages
    )
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.draw_header()

    cleaned   = clean_markdown(claude_analysis, language=language)
    lines_raw = cleaned.split("\n")

    render_items = []
    for raw_line in lines_raw:
        line = raw_line.strip()
        if not line:
            render_items.append(("blank", ""))
            continue
        if re.match(r'^\d+\.\s+[^\s]', line) and len(line) < 90:
            render_items.append(("heading", line))
        elif line.startswith("- ") or line.startswith("• ") or line.startswith("* "):
            render_items.append(("bullet", line[2:].strip()))
        else:
            render_items.append(("text", line))

    for item_type, item_text in render_items:
        if item_type == "blank":
            if pdf.get_y() + 2.5 < pdf.safe_bottom:
                pdf.ln(2.5)
        elif item_type == "heading":
            if pdf.get_y() + 3 < pdf.safe_bottom:
                pdf.ln(3)
            pdf.draw_section_heading(item_text)
            if pdf.get_y() + 1.5 < pdf.safe_bottom:
                pdf.ln(1.5)
        elif item_type == "bullet":
            pdf.draw_bullet(item_text)
        else:
            if item_text:
                pdf.draw_body_text(item_text)
                if pdf.get_y() + 1 < pdf.safe_bottom:
                    pdf.ln(1)

    if pdf.get_y() + 3 < pdf.safe_bottom:
        pdf.ln(3)
    pdf.draw_disclaimer()
    pdf.draw_management_section()
    pdf.draw_footer()
    pdf.cleanup_tmp()

    os.makedirs("static/reports", exist_ok=True)
    temp_path = f"static/reports/temp_analysis_{report_id}.pdf"
    pdf.output(temp_path)
    return temp_path, pdf.page_num


# ══════════════════════════════════════════════════════════════
#  PAGE 1
# ══════════════════════════════════════════════════════════════

def _build_page1(c, W, H, header_h, name, age, gender, phone, now,
                 logo_path, face_photo_path, img_parts, img_w, img_h,
                 card_h, gap, pill_colors, detected_labels,
                 recommendations, no_issues, report_id, total_pages):

    # ── Header bar ───────────────────────────────────────────
    c.setFillColor(C_HEADER)
    c.rect(0, H - header_h, W, header_h, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.rect(0, H - header_h, 8, header_h, fill=1, stroke=0)

    if os.path.exists(logo_path):
        logo_y = H - header_h + (header_h - 60) / 2
        try:
            c.drawImage(logo_path, 20, logo_y, width=180, height=60,
                        preserveAspectRatio=True, mask="auto")
        except Exception as e:
            print(f"[Page1] Logo error: {e}")
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

    # ── Patient info bar ─────────────────────────────────────
    bar_bottom = draw_patient_info_bar(c, W, H, header_h, name, age, gender, phone, now,
                                       face_photo_path=face_photo_path)
    cur_y = bar_bottom
    cur_y = draw_section_bar_rl(c, W, cur_y, "  AI SCREENING REPORT")
    card_y = cur_y - 14 - card_h

    # ── YOLO image cards ─────────────────────────────────────
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
            try:
                c.drawImage(img_path, ix + 5, iy2 + 28, width=img_w - 10, height=img_h,
                            preserveAspectRatio=True, mask="auto")
            except Exception as e:
                print(f"[Page1] YOLO img error: {e}")
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.8)
        c.roundRect(ix, iy2, img_w, card_h, 10, fill=0, stroke=1)
        c.setFillColor(pill_colors[i])
        c.roundRect(ix + 14, iy2 + 7, img_w - 28, 17, 8, fill=1, stroke=0)
        c.setFillColor(C_WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(ix + img_w / 2, iy2 + 12, lbl)

    # ── Detected conditions legend ────────────────────────────
    cur_y = card_y - 18
    detected = [k for k in ["malaligned", "stains", "caries", "pit_fissure"] if k in detected_labels]
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

    # ── Recommendations ───────────────────────────────────────
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

    # ── Page 1 footer ─────────────────────────────────────────
    draw_footer_rl(c, W, report_id, 1, total_pages)
    c.save()


# ══════════════════════════════════════════════════════════════
#  generate_pdf  (main entry point)
# ══════════════════════════════════════════════════════════════

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

    os.makedirs("static/reports", exist_ok=True)
    report_path = f"static/reports/{report_id}.pdf"
    logo_path   = "static/logo.png"
    face_photo_path = get_face_photo_path(screening_id, report_id)

    img_h       = 152
    img_w       = 152
    gap         = (595.27 - 56 - img_w * 3) / 4
    card_h      = img_h + 34
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

    try:
        c = rl_canvas.Canvas(report_path, pagesize=A4)
        W, H = A4
        header_h = 90
        _build_page1(c, W, H, header_h, name, age, gender, phone, now,
                     logo_path, face_photo_path, img_parts,
                     img_w, img_h, card_h, gap, pill_colors,
                     detected_labels, recommendations, no_issues,
                     report_id, total_pages=99)
        print(f"[PDF] Page 1 OK")
    except Exception as e:
        print(f"[PDF] Page 1 FAILED: {e}")
        traceback.print_exc()
        raise

    if claude_analysis:
        if PdfWriter is None or PdfReader is None:
            print("[PDF] No merge library — skipping analysis pages")
            return report_path
        try:
            temp_path, _ = generate_analysis_pages_fpdf2(
                claude_analysis=claude_analysis, language=language,
                name=name, age=age, gender=gender,
                report_id=report_id, logo_path=logo_path,
                start_page=2, total_pages=99
            )
            print(f"[PDF] Analysis pages OK")

            writer = PdfWriter()
            for page in PdfReader(report_path).pages:
                writer.add_page(page)
            for page in PdfReader(temp_path).pages:
                writer.add_page(page)
            actual_pages = len(writer.pages)
            print(f"[PDF] Total pages: {actual_pages}")

            c2 = rl_canvas.Canvas(report_path, pagesize=A4)
            _build_page1(c2, W, H, header_h, name, age, gender, phone, now,
                         logo_path, face_photo_path, img_parts,
                         img_w, img_h, card_h, gap, pill_colors,
                         detected_labels, recommendations, no_issues,
                         report_id, total_pages=actual_pages)
            try:
                os.remove(temp_path)
            except:
                pass

            temp_path2, _ = generate_analysis_pages_fpdf2(
                claude_analysis=claude_analysis, language=language,
                name=name, age=age, gender=gender,
                report_id=report_id, logo_path=logo_path,
                start_page=2, total_pages=actual_pages
            )

            writer2 = PdfWriter()
            for page in PdfReader(report_path).pages:
                writer2.add_page(page)
            for page in PdfReader(temp_path2).pages:
                writer2.add_page(page)
            with open(report_path, "wb") as f:
                writer2.write(f)
            try:
                os.remove(temp_path2)
            except:
                pass

            print(f"[PDF] Final saved: {report_path}")

        except Exception as e:
            print(f"[PDF] Merge failed: {e}")
            traceback.print_exc()
            print("[PDF] Returning page-1-only fallback")

    return report_path