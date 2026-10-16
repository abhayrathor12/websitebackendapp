from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_WIDTH = 1600
WEBP_QUALITY = 82


def to_webp(file):
    """Resize an uploaded image to at most 1600px wide and convert it to WebP.

    A 1.4 MB PNG typically becomes 100-200 KB with no visible difference,
    which makes blog pages load much faster.
    """
    file.open("rb")
    image = ImageOps.exif_transpose(Image.open(file))
    has_alpha = image.mode in ("RGBA", "LA", "P") and image.convert("RGBA").getextrema()[3][0] < 255
    image = image.convert("RGBA" if has_alpha else "RGB")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, "WEBP", quality=WEBP_QUALITY, method=6)
    return ContentFile(buffer.getvalue(), name=f"{Path(file.name).stem}.webp")
