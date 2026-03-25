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

# ─────────────────────────────────────────────
#  Brand Palette
# ─────────────────────────────────────────────
PRIMARY = colors.HexColor("#0EA5E9")  # Sky blue
DARK = colors.HexColor("#0C1A2E")  # Near-black navy
MUTED = colors.HexColor("#64748B")  # Slate gray
LIGHT_BG = colors.HexColor("#F0F9FF")  # Very light blue tint
DIVIDER = colors.HexColor("#E2E8F0")  # Light gray
RED_FLAG = colors.HexColor("#DC2626")  # Alert red
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


# ─────────────────────────────────────────────
#  Header / Footer Canvas
# ─────────────────────────────────────────────
class MedicalReportCanvas(rl_canvas.Canvas):
    """Draws the fixed letterhead header and footer on every page."""

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

        # Top accent bar
        c.setFillColor(PRIMARY)
        c.rect(0, PAGE_H - 18 * mm, w, 18 * mm, fill=1, stroke=0)

        # Clinic name
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(MARGIN, PAGE_H - 12 * mm, "MediConnect Clinic")

        # Tagline / contact on the right
        c.setFont("Helvetica", 8)
        c.drawRightString(
            w - MARGIN, PAGE_H - 8 * mm, "contact@mediconnect.com  |  +1 (800) 123-4567"
        )
        c.drawRightString(
            w - MARGIN, PAGE_H - 13 * mm, "123 Health Avenue, Wellness District"
        )

        # Thin bottom accent under header
        c.setFillColor(colors.HexColor("#0284C7"))
        c.rect(0, PAGE_H - 19.5 * mm, w, 1.5 * mm, fill=1, stroke=0)

    def _draw_footer(self, total_pages):
        c = self
        w = PAGE_W
        page_num = c.getPageNumber()

        # Footer line
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.5)
        c.line(MARGIN, 14 * mm, w - MARGIN, 14 * mm)

        # Footer text
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(
            MARGIN,
            9 * mm,
            "This is an electronically generated document based on an AI-assisted tele-consultation.",
        )
        c.setFont("Helvetica", 7.5)
        c.drawRightString(w - MARGIN, 9 * mm, f"Page {page_num} of {total_pages}")


# ─────────────────────────────────────────────
#  Style Helpers
# ─────────────────────────────────────────────
def _style(name, **kwargs):
    defaults = dict(
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=DARK,
        spaceAfter=0,
        spaceBefore=0,
    )
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


S_SECTION_TITLE = _style(
    "SectionTitle",
    fontName="Helvetica-Bold",
    fontSize=8,
    textColor=MUTED,
    spaceAfter=4,
    leading=10,
)
S_FIELD_LABEL = _style(
    "FieldLabel", fontName="Helvetica-Bold", fontSize=9, textColor=DARK, leading=13
)
S_FIELD_VALUE = _style(
    "FieldValue", fontName="Helvetica", fontSize=9, textColor=DARK, leading=13
)
S_RX_TITLE = _style(
    "RxTitle", fontName="Helvetica-Bold", fontSize=26, textColor=PRIMARY, leading=30
)
S_RX_SUB = _style(
    "RxSub", fontName="Helvetica-Bold", fontSize=11, textColor=DARK, leading=14
)
S_BODY = _style("Body", fontName="Helvetica", fontSize=10, textColor=DARK, leading=15)
S_FOLLOWUP = _style(
    "FollowUp", fontName="Helvetica-Bold", fontSize=10, textColor=RED_FLAG, leading=14
)
S_SIG_LINE = _style(
    "SigLine",
    fontName="Helvetica",
    fontSize=9,
    textColor=MUTED,
    alignment=TA_CENTER,
    leading=12,
)
S_PRIORITY_HIGH = _style(
    "PriorityHigh",
    fontName="Helvetica-Bold",
    fontSize=9,
    textColor=RED_FLAG,
    leading=13,
)
S_PRIORITY_MED = _style(
    "PriorityMed",
    fontName="Helvetica-Bold",
    fontSize=9,
    textColor=colors.HexColor("#D97706"),
    leading=13,
)
S_PRIORITY_LOW = _style(
    "PriorityLow",
    fontName="Helvetica-Bold",
    fontSize=9,
    textColor=colors.HexColor("#16A34A"),
    leading=13,
)


def _divider(color=DIVIDER, thickness=0.5):
    return HRFlowable(
        width="100%", thickness=thickness, color=color, spaceAfter=6, spaceBefore=6
    )


def _section_header(label: str):
    """A compact uppercase section label with a colored left bar (via table trick)."""
    bar = Table([[""]], colWidths=[3], rowHeights=[12])
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
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
    """Returns a coloured priority label."""
    if score >= 8:
        style, label = S_PRIORITY_HIGH, f"🔴  PRIORITY {score}/10 — URGENT"
    elif score >= 5:
        style, label = S_PRIORITY_MED, f"🟡  PRIORITY {score}/10 — MODERATE"
    else:
        style, label = S_PRIORITY_LOW, f"🟢  PRIORITY {score}/10 — ROUTINE"
    return Paragraph(label, style)


# ─────────────────────────────────────────────
#  Main Generator
# ─────────────────────────────────────────────
def generate_medical_report(
    patient_name,
    date_str,
    summary_json,
    doctor_notes,
    filename,
    follow_up_days=None,
):
    output_folder = "uploaded_files"
    os.makedirs(output_folder, exist_ok=True)
    file_path = os.path.join(output_folder, filename)

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=28 * mm,  # space below header bar
        bottomMargin=22 * mm,
    )

    story = []

    # ── Patient Info Card ─────────────────────────────────────────────
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
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEAFTER", (1, 0), (1, 0), 0.5, DIVIDER),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 10 * mm))

    # ── Rx Section ────────────────────────────────────────────────────
    story.append(_section_header("Prescription"))
    story.append(Spacer(1, 4 * mm))

    story.append(
        KeepTogether(
            [
                Paragraph("Rx", S_RX_TITLE),
                Paragraph("Doctor's Notes &amp; Medications", S_RX_SUB),
                Spacer(1, 3 * mm),
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

    # Signature block
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
                ("TEXTCOLOR", (1, 1), (1, 1), MUTED),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(sig_table)
    story.append(Spacer(1, 10 * mm))

    # ── Clinical Triage Details ───────────────────────────────────────
    if summary_json:
        story.append(_divider(PRIMARY, 1))
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
                textColor=colors.HexColor("#1E40AF"),
                leading=13,
            )
            note_data = [[Paragraph(f"&quot;{summary_note}&quot;", note_style)]]
            note_table = Table(note_data, colWidths=["*"])
            note_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFDBFE")),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ]
                )
            )
            story.append(note_table)
            story.append(Spacer(1, 5 * mm))

        # Keys to skip on the PDF (doctor-dashboard only)
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
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, DIVIDER),
            ]
            # Alternate row shading
            for i in range(0, len(field_rows), 2):
                row_styles.append(("BACKGROUND", (0, i), (-1, i), LIGHT_BG))

            field_table.setStyle(TableStyle(row_styles))
            story.append(field_table)

    # ── Build ─────────────────────────────────────────────────────────
    doc.build(story, canvasmaker=MedicalReportCanvas)
    return file_path
