"""Certificate PDF (reportlab), certificate IDs and the verification QR code.

Design: "Option 1 - Classic" (cream page, navy + gold frame, seal, signature, QR code).
The QR code opens the website's /verify-certificate page for this certificate ID.
"""

import math
import secrets
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from reportlab.graphics.barcode import qrencoder
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

NAVY = HexColor("#203f78")
NAVY_DEEP = HexColor("#142a54")
GOLD = HexColor("#ddaf26")
INK = HexColor("#1a2740")
SOFT = HexColor("#5b6478")
CREAM = HexColor("#fbf8ef")

COURSE = "Smart Manufacturing & AI Masterclass 2026"
ORGANISATION = "Technoviz Automation"
TRAINER = "Kapil Khurana"

ASSETS = Path(__file__).resolve().parent / "certificate_assets"

# ─── Certificate IDs ───

ID_PREFIX = "TVA-MC26-"
# No 0/O, 1/I/L - easy to read and type from the printed certificate
ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_certificate_id():
    """Random, hard-to-guess ID, e.g. TVA-MC26-7K3F9Q (uniqueness is checked by the caller)."""
    return ID_PREFIX + "".join(secrets.choice(ID_ALPHABET) for _ in range(6))


def normalise_certificate_id(value):
    """What a visitor typed -> the stored format ('tva-mc26-7k3f9q ' -> 'TVA-MC26-7K3F9Q')."""
    return "".join(str(value or "").split()).upper()


def verify_url(cert_id):
    """Link in the QR code: the website's verification page, with the ID filled in."""
    base = getattr(
        settings, "CERTIFICATE_VERIFY_URL", "https://www.technovizautomation.com/verify-certificate"
    )
    return f"{base}?id={quote(cert_id)}"


def qr_matrix(text):
    """QR code as rows of '1' (dark) / '0' (light). Also used by the on-screen preview."""
    qr = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    qr.addData(text)
    qr.make()
    n = qr.getModuleCount()
    return ["".join("1" if qr.isDark(r, c) else "0" for c in range(n)) for r in range(n)]


# ─── Drawing helpers ───


def _spaced(c, x, y, text, font, size, space):
    """Letter-spaced text, centred on x. Returns its width."""
    width = c.stringWidth(text, font, size) + space * (len(text) - 1)
    c.saveState()  # keeps the spacing from leaking into later text
    t = c.beginText(x - width / 2, y)
    t.setFont(font, size)
    t.setCharSpace(space)
    t.textOut(text)
    c.drawText(t)
    c.restoreState()
    return width


def _fit_font_size(c, text, font, max_size, max_width, min_size=18):
    size = max_size
    while size > min_size and c.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _image(c, path, cx, y, width):
    img = ImageReader(str(path))
    iw, ih = img.getSize()
    c.drawImage(img, cx - width / 2, y, width, width * ih / iw, mask="auto")


def _star(c, cx, cy, r):
    p = c.beginPath()
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def _circle_text(c, cx, cy, r, text, font, size):
    """Text along the top of a circle."""
    c.setFont(font, size)
    widths = [c.stringWidth(ch, font, size) for ch in text]
    step = 1.15 * 180 / (math.pi * r)  # degrees per point of text
    a = 90 + sum(widths) * step / 2
    for ch, w in zip(text, widths):
        a -= w * step / 2
        rad = math.radians(a)
        c.saveState()
        c.translate(cx + r * math.cos(rad), cy + r * math.sin(rad))
        c.rotate(a - 90)
        c.drawCentredString(0, 0, ch)
        c.restoreState()
        a -= w * step / 2


def _seal(c, cx, cy, r):
    """Round gold 'AI Masterclass 2026' seal."""
    c.setFillColor(GOLD)
    p = c.beginPath()
    teeth = 36
    for i in range(teeth * 2):
        a = math.pi * 2 * i / (teeth * 2)
        rr = r if i % 2 == 0 else r * 0.93
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.circle(cx, cy, r * 0.84, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.circle(cx, cy, r * 0.62, stroke=1, fill=0)
    c.setFillColor(GOLD)
    _circle_text(c, cx, cy, r * 0.68, "TECHNOVIZ AUTOMATION", "Helvetica-Bold", r * 0.13)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", r * 0.2)
    c.drawCentredString(cx, cy + r * 0.06, "AI")
    c.setFont("Helvetica", r * 0.12)
    c.drawCentredString(cx, cy - r * 0.15, "MASTERCLASS")
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", r * 0.14)
    c.drawCentredString(cx, cy - r * 0.36, "2026")
    for side in (-1, 1):
        _star(c, cx + side * r * 0.42, cy + r * 0.1, r * 0.06)


def _qr(c, x, y, size, text):
    """QR code with its bottom-left corner at (x, y) on a white tile."""
    rows = qr_matrix(text)
    n = len(rows)
    pad = size * 0.06
    c.setFillColor(white)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.rect(x - pad, y - pad, size + 2 * pad, size + 2 * pad, stroke=1, fill=1)
    cell = size / n
    c.setFillColor(NAVY_DEEP)
    for r, row in enumerate(rows):
        for col, dark in enumerate(row):
            if dark == "1":
                # tiny overlap so no hairlines show between modules
                c.rect(x + col * cell, y + size - (r + 1) * cell, cell + 0.15, cell + 0.15, stroke=0, fill=1)


# ─── Certificate ───


def build_certificate_pdf(name, completed_on, cert_id):
    """Returns the certificate as PDF bytes. completed_on is a date/datetime."""
    buffer = BytesIO()
    width, height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setTitle(f"Certificate - {name}")
    c.setAuthor(ORGANISATION)
    cx = width / 2

    # Page, frames and gold corners
    c.setFillColor(CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    c.setStrokeColor(NAVY)
    c.setLineWidth(12)
    c.rect(16, 16, width - 32, height - 32)
    c.setStrokeColor(GOLD)
    c.setLineWidth(2.2)
    c.rect(32, 32, width - 64, height - 64)
    c.setLineWidth(0.7)
    c.rect(38, 38, width - 76, height - 76)
    for x, y, sx, sy in (
        (38, 38, 1, 1),
        (width - 38, 38, -1, 1),
        (38, height - 38, 1, -1),
        (width - 38, height - 38, -1, -1),
    ):
        c.setFillColor(GOLD)
        p = c.beginPath()
        p.moveTo(x, y)
        p.lineTo(x + sx * 46, y)
        p.lineTo(x, y + sy * 46)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.circle(x + sx * 12, y + sy * 12, 3.2, stroke=0, fill=1)

    _image(c, ASSETS / "logo_light.png", cx, height - 112, 170)

    # CERTIFICATE (big) / OF COMPLETION (small)
    c.setFillColor(NAVY_DEEP)
    _spaced(c, cx, height - 178, "CERTIFICATE", "Times-Bold", 62, 7)
    c.setFillColor(GOLD)
    text_w = _spaced(c, cx, height - 205, "OF COMPLETION", "Helvetica-Bold", 13, 6)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    for side in (-1, 1):
        x0 = cx + side * (text_w / 2 + 14)
        c.line(x0, height - 200, x0 + side * 70, height - 200)

    # Body
    c.setFillColor(SOFT)
    c.setFont("Times-Italic", 16)
    c.drawCentredString(cx, height - 245, "This is to certify that")

    name_size = _fit_font_size(c, name, "Times-BoldItalic", 46, width - 220)
    c.setFillColor(NAVY)
    c.setFont("Times-BoldItalic", name_size)
    c.drawCentredString(cx, height - 298, name)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.4)
    c.line(cx - 230, height - 312, cx + 230, height - 312)

    c.setFillColor(SOFT)
    c.setFont("Helvetica", 13.5)
    c.drawCentredString(cx, height - 340, "has successfully completed the Full-Day")
    c.setFillColor(NAVY_DEEP)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(cx, height - 368, COURSE)
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 12)
    c.drawCentredString(cx, height - 388, f"conducted by {ORGANISATION}")

    # Footer: date | seal | signature | QR code
    footer_y = 112
    date_x, seal_x, sign_x, qr_x = width * 0.19, width * 0.415, width * 0.635, width * 0.855
    line_w = 170

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(date_x, footer_y + 10, completed_on.strftime("%d %B %Y"))
    c.setStrokeColor(SOFT)
    c.setLineWidth(0.8)
    c.line(date_x - line_w / 2, footer_y, date_x + line_w / 2, footer_y)
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(date_x, footer_y - 17, "Date of Completion")

    _seal(c, seal_x, footer_y - 4, 46)

    _image(c, ASSETS / "signature.png", sign_x, footer_y + 6, 124)
    c.setStrokeColor(SOFT)
    c.line(sign_x - line_w / 2, footer_y, sign_x + line_w / 2, footer_y)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(sign_x, footer_y - 17, TRAINER)
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(sign_x, footer_y - 31, "Trainer")

    qr_size = 74
    _qr(c, qr_x - qr_size / 2, footer_y - 36, qr_size, verify_url(cert_id))
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(qr_x, footer_y - 54, "Scan to verify")

    c.setFont("Helvetica", 9)
    c.drawCentredString(cx, 47, f"Certificate ID: {cert_id}")

    c.showPage()
    c.save()
    return buffer.getvalue()
