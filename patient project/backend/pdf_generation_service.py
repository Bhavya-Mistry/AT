import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
from reportlab.pdfgen import canvas as rl_canvas

# ─────────────────────────────────────────────────────────────
#  ClinIQ Print Palette — Professional Warm White
#  Brand gold accent (#C9A96E) retained from frontend identity
#  Background: warm white/beige for print-friendly output
# ─────────────────────────────────────────────────────────────
PAGE_BG = colors.HexColor("#FDFBF7")  # warm off-white base
SURFACE = colors.HexColor("#F5F1EA")  # slightly warm beige for alternating rows
CARD = colors.HexColor("#F0EBE0")  # card background (beige)
ACCENT = colors.HexColor("#C9A96E")  # ClinIQ gold — primary brand colour
ACCENT_DARK = colors.HexColor("#A07040")  # deeper gold for rules and borders
ACCENT_DIM = colors.HexColor("#FAF3E4")  # very pale gold tint for callout boxes
DARK = colors.HexColor("#1A1714")  # near-black for headings
TEXT = colors.HexColor("#2C2825")  # main body text
TEXT_DIM = colors.HexColor("#6B635A")  # secondary / dim text
TEXT_FAINT = colors.HexColor("#9E948A")  # faint / footer text
BORDER = colors.HexColor("#E2D9CC")  # warm light border
RED = colors.HexColor("#C0392B")  # urgent red (print-safe)
AMBER = colors.HexColor("#B7860B")  # moderate amber (print-safe)
GREEN = colors.HexColor("#27774A")  # routine green (print-safe)
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


# ─────────────────────────────────────────────────────────────
#  Header / Footer Canvas
# ─────────────────────────────────────────────────────────────
class MedicalReportCanvas(rl_canvas.Canvas):
    """Draws the fixed ClinIQ letterhead header and footer on every page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header()
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_header(self):
        c = self
        w = PAGE_W
        header_h = 20 * mm

        # ── Warm white header background ─────────────────────
        c.setFillColor(WHITE)
        c.rect(0, PAGE_H - header_h, w, header_h, fill=1, stroke=0)

        # ── Left gold accent stripe ──────────────────────────
        c.setFillColor(ACCENT)
        c.rect(0, PAGE_H - header_h, 5, header_h, fill=1, stroke=0)

        # ── Logo mark (small rounded square) ────────────────
        logo_x, logo_y = MARGIN + 2, PAGE_H - header_h + 4 * mm
        logo_size = 10 * mm
        c.setFillColor(ACCENT)
        c.roundRect(logo_x, logo_y, logo_size, logo_size, 2 * mm, fill=1, stroke=0)

        # "C" glyph inside logo mark
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(logo_x + logo_size / 2, logo_y + 3 * mm, "C")

        # ── Brand name "ClinIQ" ──────────────────────────────
        name_x = logo_x + logo_size + 4 * mm
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(name_x, logo_y + 3.5 * mm, "Clin")
        name_offset = c.stringWidth("Clin", "Helvetica-Bold", 15)
        c.setFillColor(ACCENT)
        c.drawString(name_x + name_offset, logo_y + 3.5 * mm, "IQ")

        # ── Tagline below name ───────────────────────────────
        c.setFillColor(TEXT_FAINT)
        c.setFont("Helvetica", 7)
        c.drawString(name_x, logo_y + 0.2 * mm, "The IQ your clinic never had.")

        # ── Contact info right-aligned ───────────────────────
        c.setFillColor(TEXT_DIM)
        c.setFont("Helvetica", 7.5)
        c.drawRightString(
            w - MARGIN, PAGE_H - 7 * mm, "contact@cliniq.com  |  +1 (800) 123-4567"
        )
        c.drawRightString(
            w - MARGIN, PAGE_H - 11 * mm, "123 Health Avenue, Wellness District"
        )

        # ── Gold bottom rule ─────────────────────────────────
        c.setFillColor(ACCENT)
        c.rect(0, PAGE_H - header_h - 1 * mm, w, 1 * mm, fill=1, stroke=0)

    def _draw_footer(self, total_pages):
        c = self
        w = PAGE_W
        page_num = c.getPageNumber()

        # Footer warm beige strip
        c.setFillColor(SURFACE)
        c.rect(0, 0, w, 16 * mm, fill=1, stroke=0)

        # Gold top rule on footer
        c.setFillColor(ACCENT)
        c.rect(0, 16 * mm, w, 0.8 * mm, fill=1, stroke=0)

        # Disclaimer text
        c.setFillColor(TEXT_FAINT)
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(
            MARGIN,
            9 * mm,
            "This is an electronically generated document based on an AI-assisted tele-consultation.",
        )

        # Confidential badge
        badge_w = 42 * mm
        badge_x = MARGIN
        c.setFillColor(ACCENT_DIM)
        c.roundRect(badge_x, 3.5 * mm, badge_w, 4 * mm, 1 * mm, fill=1, stroke=0)
        c.setStrokeColor(ACCENT)
        c.setLineWidth(0.4)
        c.roundRect(badge_x, 3.5 * mm, badge_w, 4 * mm, 1 * mm, fill=0, stroke=1)
        c.setFillColor(ACCENT_DARK)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(
            badge_x + badge_w / 2, 4.8 * mm, "CONFIDENTIAL MEDICAL RECORD"
        )

        # Page number right
        c.setFillColor(TEXT_FAINT)
        c.setFont("Helvetica", 7.5)
        c.drawRightString(w - MARGIN, 9 * mm, f"Page {page_num} of {total_pages}")


# ─────────────────────────────────────────────────────────────
#  Style Helpers
# ─────────────────────────────────────────────────────────────
def _style(name, **kwargs):
    defaults = dict(
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=TEXT,
        spaceAfter=0,
        spaceBefore=0,
        backColor=None,
    )
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


S_SECTION_TITLE = _style(
    "SectionTitle",
    fontName="Helvetica-Bold",
    fontSize=7.5,
    textColor=ACCENT_DARK,
    spaceAfter=4,
    leading=10,
)
S_FIELD_LABEL = _style(
    "FieldLabel", fontName="Helvetica-Bold", fontSize=8.5, textColor=DARK, leading=13
)
S_FIELD_VALUE = _style(
    "FieldValue", fontName="Helvetica", fontSize=9, textColor=TEXT, leading=13
)
S_RX_TITLE = _style(
    "RxTitle", fontName="Helvetica-Bold", fontSize=28, textColor=ACCENT, leading=32
)
S_RX_SUB = _style(
    "RxSub", fontName="Helvetica-Bold", fontSize=11, textColor=DARK, leading=14
)
S_BODY = _style("Body", fontName="Helvetica", fontSize=9.5, textColor=TEXT, leading=15)
S_FOLLOWUP = _style(
    "FollowUp",
    fontName="Helvetica-Bold",
    fontSize=10,
    textColor=ACCENT_DARK,
    leading=14,
)
S_SIG_LINE = _style(
    "SigLine",
    fontName="Helvetica",
    fontSize=9,
    textColor=TEXT_FAINT,
    alignment=TA_CENTER,
    leading=12,
)
S_PRIORITY_HIGH = _style(
    "PriorityHigh", fontName="Helvetica-Bold", fontSize=9, textColor=RED, leading=13
)
S_PRIORITY_MED = _style(
    "PriorityMed", fontName="Helvetica-Bold", fontSize=9, textColor=AMBER, leading=13
)
S_PRIORITY_LOW = _style(
    "PriorityLow", fontName="Helvetica-Bold", fontSize=9, textColor=GREEN, leading=13
)


def _divider(color=ACCENT_DARK, thickness=0.5):
    return HRFlowable(
        width="100%", thickness=thickness, color=color, spaceAfter=6, spaceBefore=6
    )


def _section_header(label: str):
    """Compact uppercase section label with gold left accent bar."""
    bar = Table([[""]], colWidths=[3], rowHeights=[12])
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    text = Table(
        [[Paragraph(label.upper(), S_SECTION_TITLE)]], colWidths=["*"], rowHeights=[12]
    )
    text.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT_DIM),
            ]
        )
    )
    combo = Table([[bar, text]], colWidths=[3, "*"])
    combo.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return combo


def _priority_badge(score: int):
    """Returns a coloured priority label matching ClinIQ status colors."""
    if score >= 8:
        style, label = S_PRIORITY_HIGH, f"PRIORITY {score}/10  -  URGENT"
    elif score >= 5:
        style, label = S_PRIORITY_MED, f"PRIORITY {score}/10  -  MODERATE"
    else:
        style, label = S_PRIORITY_LOW, f"PRIORITY {score}/10  -  ROUTINE"

    badge_color = RED if score >= 8 else (AMBER if score >= 5 else GREEN)
    bg_color = (
        colors.HexColor("#FDF0EE")
        if score >= 8
        else (colors.HexColor("#FDF8EE") if score >= 5 else colors.HexColor("#EEF7F2"))
    )

    data = [[Paragraph(label, style)]]
    t = Table(data, colWidths=["*"])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                ("BOX", (0, 0), (-1, -1), 0.8, badge_color),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return t


# ─────────────────────────────────────────────────────────────
#  Main Generator
# ─────────────────────────────────────────────────────────────
def generate_medical_report(
    patient_name,
    date_str,
    summary_json,
    doctor_notes,
    filename,
    follow_up_days=None,
):
    # output_folder = "uploaded_files"
    # os.makedirs(output_folder, exist_ok=True)
    file_path = f"temp_{filename}"

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=30 * mm,  # space below header bar
        bottomMargin=24 * mm,
    )

    story = []

    # ── Patient Info Card ────────────────────────────────────
    info_data = [
        [
            Paragraph("<b>Patient</b>", S_FIELD_LABEL),
            Paragraph(patient_name, S_FIELD_VALUE),
            Paragraph("<b>Date</b>", S_FIELD_LABEL),
            Paragraph(date_str, S_FIELD_VALUE),
        ]
    ]
    info_table = Table(info_data, colWidths=[28 * mm, 75 * mm, 20 * mm, 45 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LINEAFTER", (1, 0), (1, 0), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # Gold left border on card
                ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 10 * mm))

    # ── Rx Section ───────────────────────────────────────────
    story.append(_section_header("Prescription"))
    story.append(Spacer(1, 4 * mm))

    story.append(
        KeepTogether(
            [
                Paragraph("Rx", S_RX_TITLE),
                Paragraph("Doctor's Notes &amp; Medications", S_RX_SUB),
                Spacer(1, 3 * mm),
                _divider(ACCENT_DARK, 0.4),
                Spacer(1, 2 * mm),
                Paragraph(doctor_notes.replace("\n", "<br/>"), S_BODY),
            ]
        )
    )

    if follow_up_days:
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                f"&#9658;  Follow-up required in <b>{follow_up_days} days</b>",
                S_FOLLOWUP,
            )
        )

    # ── Signature block ──────────────────────────────────────
    story.append(Spacer(1, 12 * mm))
    sig_data = [
        ["", "_______________________________"],
        ["", "Attending Doctor Signature"],
    ]
    sig_table = Table(sig_data, colWidths=["*", 65 * mm])
    sig_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("FONTNAME", (1, 1), (1, 1), "Helvetica"),
                ("FONTSIZE", (1, 1), (1, 1), 8),
                ("TEXTCOLOR", (1, 0), (1, 0), ACCENT_DARK),
                ("TEXTCOLOR", (1, 1), (1, 1), TEXT_FAINT),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(sig_table)
    story.append(Spacer(1, 10 * mm))

    # ── Clinical Triage Details ──────────────────────────────
    if summary_json:
        story.append(_divider(ACCENT, 0.8))
        story.append(Spacer(1, 3 * mm))
        story.append(_section_header("Clinical Triage Details  (AI Generated)"))
        story.append(Spacer(1, 5 * mm))

        # Priority badge
        priority_score = summary_json.get("priority_score")
        if isinstance(priority_score, (int, float)):
            story.append(_priority_badge(int(priority_score)))
            story.append(Spacer(1, 4 * mm))

        # Summary note callout box
        summary_note = summary_json.get("summary_note", "")
        if summary_note and summary_note not in ("None", "Not reported"):
            note_style = _style(
                "NoteBox",
                fontName="Helvetica-Oblique",
                fontSize=9,
                textColor=ACCENT_DARK,
                leading=13,
            )
            note_data = [[Paragraph(f'"{summary_note}"', note_style)]]
            note_table = Table(note_data, colWidths=["*"])
            note_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_DIM),
                        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
                        ("TOPPADDING", (0, 0), (-1, -1), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                        ("LEFTPADDING", (0, 0), (-1, -1), 12),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ]
                )
            )
            story.append(note_table)
            story.append(Spacer(1, 5 * mm))

        # Keys to hide from PDF (doctor-dashboard only)
        hidden_keys = {
            "patient_language",
            "reviewed",
            "priority_score",
            "summary_note",
            "recommended_action",
        }

        # Two-column field grid
        field_rows = []
        for key, value in summary_json.items():
            if key in hidden_keys:
                continue
            if not value or value in ("None", "Not reported"):
                continue

            clean_key = key.replace("_", " ").title()
            clean_val = ", ".join(value) if isinstance(value, list) else str(value)

            field_rows.append(
                [
                    Paragraph(clean_key, S_FIELD_LABEL),
                    Paragraph(clean_val, S_FIELD_VALUE),
                ]
            )

        if field_rows:
            col_w = PAGE_W - 2 * MARGIN
            field_table = Table(field_rows, colWidths=[45 * mm, col_w - 45 * mm])
            row_styles = [
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORDER),
            ]
            # Alternate row shading — warm beige tones
            for i in range(0, len(field_rows), 2):
                row_styles.append(("BACKGROUND", (0, i), (-1, i), WHITE))
            for i in range(1, len(field_rows), 2):
                row_styles.append(("BACKGROUND", (0, i), (-1, i), SURFACE))

            field_table.setStyle(TableStyle(row_styles))
            story.append(field_table)

    # ── Build ────────────────────────────────────────────────
    doc.build(story, canvasmaker=MedicalReportCanvas)
    return file_path
