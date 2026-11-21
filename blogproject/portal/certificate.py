"""Builds the simple certificate PDF (reportlab)."""

from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

NAVY = HexColor("#203f78")
NAVY_DEEP = HexColor("#142a54")
GOLD = HexColor("#ddaf26")
INK = HexColor("#1a2740")
SOFT = HexColor("#5b6478")

COURSE = "Smart Manufacturing & AI Masterclass 2026"
ORGANISATION = "Technoviz Automation"
TRAINER = "Kapil Khurana"


def certificate_id(user_id):
    return f"TVA-MC26-{user_id:05d}"


def _fit_font_size(c, text, font, max_size, max_width, min_size=18):
    size = max_size
    while size > min_size and c.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def build_certificate_pdf(name, completed_on, cert_id):
    """Returns the certificate as PDF bytes. completed_on is a date/datetime."""
    buffer = BytesIO()
    width, height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setTitle(f"Certificate - {name}")
    c.setAuthor(ORGANISATION)

    # Background and borders
    c.setFillColor(HexColor("#fbfaf6"))
    c.rect(0, 0, width, height, stroke=0, fill=1)

    c.setStrokeColor(NAVY)
    c.setLineWidth(10)
    c.rect(18, 18, width - 36, height - 36, stroke=1, fill=0)

    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.rect(34, 34, width - 68, height - 68, stroke=1, fill=0)

    # Top band
    c.setFillColor(NAVY)
    c.rect(34, height - 120, width - 68, 86, stroke=0, fill=1)
    c.setFillColor(GOLD)
    c.rect(34, height - 124, width - 68, 4, stroke=0, fill=1)

    cx = width / 2
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(cx, height - 80, "CERTIFICATE OF COMPLETION")
    c.setFillColor(GOLD)
    c.setFont("Helvetica", 12)
    c.drawCentredString(cx, height - 104, ORGANISATION.upper())

    # Body
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 15)
    c.drawCentredString(cx, height - 185, "This is to certify that")

    name_size = _fit_font_size(c, name, "Helvetica-Bold", 38, width - 200)
    c.setFillColor(NAVY_DEEP)
    c.setFont("Helvetica-Bold", name_size)
    c.drawCentredString(cx, height - 240, name)

    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.line(cx - 220, height - 256, cx + 220, height - 256)

    c.setFillColor(SOFT)
    c.setFont("Helvetica", 15)
    c.drawCentredString(cx, height - 292, "has successfully completed all evaluations of the")

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(cx, height - 326, COURSE)

    c.setFillColor(SOFT)
    c.setFont("Helvetica", 13)
    c.drawCentredString(cx, height - 352, f"conducted by {ORGANISATION}")

    # Footer: date, signature, certificate ID
    footer_y = 108
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(width * 0.25, footer_y, completed_on.strftime("%d %B %Y"))
    c.drawCentredString(width * 0.75, footer_y, TRAINER)

    c.setStrokeColor(SOFT)
    c.setLineWidth(0.8)
    for x in (width * 0.25, width * 0.75):
        c.line(x - 95, footer_y - 8, x + 95, footer_y - 8)

    c.setFillColor(SOFT)
    c.setFont("Helvetica", 11)
    c.drawCentredString(width * 0.25, footer_y - 24, "Date of Completion")
    c.drawCentredString(width * 0.75, footer_y - 24, "Trainer")

    c.setFont("Helvetica", 9.5)
    c.drawCentredString(cx, 52, f"Certificate ID: {cert_id}")

    c.showPage()
    c.save()
    return buffer.getvalue()
