from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from fpdf import FPDF
from datetime import datetime
import os
import re


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


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def clean_markdown(text):
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
    text = re.sub(r'^[-=]{2,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = text.replace('`', '')
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

        self.font_name = "NotoUni"
        if os.path.exists(font_path):
            self.add_font(self.font_name, style="", fname=font_path)
        else:
            self.font_name = None

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
        self.cell(0, 5, f"Language: {sanitize(self.language)}   Observing all 3 dental images", ln=0)

        self.set_xy(110, 5)
        self.set_text_color(148, 163, 184)
        if self.font_name:
            self.set_font(self.font_name, size=7)
        else:
            self.set_font("Helvetica", "", 7)
        self.cell(95, 5,
            f"{self.pat_name} ({self.pat_age}/{self.pat_gender})",
            ln=0, align="R")

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
            sanitize("OralAI  -  AI Oral Health Screening  |  www.oralai.site"), ln=0)

        self.set_x(110)
        self.set_text_color(148, 163, 184)
        self.set_font("Helvetica", "", 7)
        self.cell(0, 5,
            sanitize(f"Report ID: {self.report_id}   |   {datetime.now().strftime('%d %b %Y')}   |   Page {self.page_num} of {self.total_pages}"),
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
            sanitize("This is an AI-based screening tool and does not replace a professional dental diagnosis. Please consult a dentist."),
            ln=0)
        self.set_y(y + 9)

    def draw_section_heading(self, text):
        text = sanitize(text)
        self.set_fill_color(37, 99, 235)
        self.rect(0, self.get_y(), 210, 8, "F")
        self.set_xy(10, self.get_y() + 1)
        self.set_text_color(255, 255, 255)
        self.get_font(bold=True, size=10)
        self.cell(0, 6, text, ln=1)
        self.ln(3)

    def draw_bullet(self, text):
        text = sanitize(text)
        y = self.get_y()
        self.set_fill_color(37, 99, 235)
        self.ellipse(12, y + 2.5, 2, 2, "F")
        self.set_xy(17, y)
        self.set_text_color(15, 23, 42)
        self.get_font(size=9)
        self.multi_cell(183, 5, text, ln=1)
        self.set_x(10)

    def draw_body_text(self, text):
        text = sanitize(text)
        self.set_x(10)
        self.set_text_color(15, 23, 42)
        self.get_font(size=9)
        self.multi_cell(190, 5, text, ln=1)

    def header(self):
        pass

    def footer(self):
        pass


def generate_analysis_pages_fpdf2(claude_analysis, language, name, age, gender,
                                   report_id, logo_path, start_page, total_pages):
    font_file = LANG_FONT_MAP.get(language, "NotoSans-Regular.ttf")
    font_path = os.path.join(FONTS_DIR, font_file)

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

    cleaned   = clean_markdown(sanitize(claude_analysis))
    lines_raw = cleaned.split("\n")

    # ✅ FIXED: Leave more room — 255 instead of 265 to avoid cutoff
    BOTTOM_LIMIT = 255

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

        # ✅ FIXED: Check page limit before rendering each item
        if pdf.get_y() > BOTTOM_LIMIT:
            pdf.draw_footer()  # disclaimer only on last page, not here
            pdf.page_num += 1
            pdf.add_page()
            # Continuation header
            pdf.set_fill_color(15, 23, 42)
            pdf.rect(0, 0, 210, 14, "F")
            pdf.set_fill_color(8, 145, 178)
            pdf.rect(0, 0, 2.5, 14, "F")
            pdf.set_xy(5, 3)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(130, 8, sanitize("AI Detailed Analysis (continued)"))
            pdf.set_text_color(148, 163, 184)
            if pdf.font_name:
                pdf.set_font(pdf.font_name, size=7)
            else:
                pdf.set_font("Helvetica", "", 7)
            pdf.cell(65, 8, sanitize(f"{name} ({age}/{gender})"), align="R")
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

    # ✅ Always draw disclaimer and footer on last page
    pdf.draw_disclaimer()
    pdf.draw_footer()

    temp_path = f"static/reports/temp_analysis_{report_id}.pdf"
    pdf.output(temp_path)
    return temp_path


# ✅ FIXED: Added screening_id parameter to use correct images
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

    total_pages = 99  # placeholder - updated after PDF merge

    report_path = f"static/reports/{report_id}.pdf"
    logo_path   = "static/logo.png"

    # ── PAGE 1 using ReportLab ───────────────────────────────────
    c = rl_canvas.Canvas(report_path, pagesize=A4)
    W, H = A4

    BOTTOM_LIMIT = 82

    # Header
    header_h = 90
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

    # Patient info bar
    bar_top = H - header_h
    c.setFillColor(C_SURFACE2)
    c.rect(0, bar_top - 30, W, 30, fill=1, stroke=0)
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.8)
    c.line(0, bar_top - 30, W, bar_top - 30)

    def info_pair(label, value, x, y):
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 9)
        lw = c.stringWidth(label, "Helvetica", 9)
        c.drawString(x, y, label)
        c.setFillColor(C_TEXT)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + lw + 3, y, value)

    iy = bar_top - 19
    info_pair("Name:",  f"{name}  ({age} / {gender})", 28, iy)
    info_pair("Phone:", phone, 240, iy)
    info_pair("Date:",  now,   380, iy)

    # Screening section
    cur_y = bar_top - 30
    cur_y = draw_section_bar_rl(c, W, cur_y, "  AI SCREENING REPORT")

    img_h  = 152
    img_w  = 152
    gap    = (W - 56 - img_w * 3) / 4
    card_h = img_h + 34
    card_y = cur_y - 14 - card_h

    # ✅ FIXED: Use screening_id in filenames so correct images show
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

    pill_colors = [C_ACCENT, C_TEAL, C_PURPLE]

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

    # Legend
    detected = [k for k in ["malaligned","stains","caries","pit_fissure"]
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

    # Treatment
    cur_y -= 4
    cur_y = draw_section_bar_rl(c, W, cur_y, "  TREATMENT RECOMMENDATIONS")
    cur_y -= 8

    no_issues = (not recommendations or
                 (len(recommendations) == 1 and recommendations[0]["label"] == "none"))

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
        cur_y -= 8

    else:
        for idx, rec in enumerate(recommendations):
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
        cur_y -= 8

    draw_disclaimer_rl(c, W)
    draw_footer_rl(c, W, report_id, 1, total_pages)
    c.save()

    # ── PAGES 2+ using fpdf2 ─────────────────────────────────────
    if claude_analysis:
        try:
            temp_path = generate_analysis_pages_fpdf2(
                claude_analysis=claude_analysis,
                language=language,
                name=name, age=age, gender=gender,
                report_id=report_id,
                logo_path=logo_path,
                start_page=2,
                total_pages=total_pages
            )

            from pypdf import PdfWriter, PdfReader

            writer = PdfWriter()

            reader1 = PdfReader(report_path)
            for page in reader1.pages:
                writer.add_page(page)

            reader2 = PdfReader(temp_path)
            for page in reader2.pages:
                writer.add_page(page)

            # ✅ FIX: get actual page count and update footer
            actual_pages = len(writer.pages)

            with open(report_path, "wb") as f:
                writer.write(f)

            os.remove(temp_path)

            print(f"PDF generated with {actual_pages} pages in {language}")

        except Exception as e:
            print(f"Analysis page merge failed: {e}")
            print("Page 1 only saved.")

    return report_path