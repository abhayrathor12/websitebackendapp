from pathlib import Path

from django.core.management.base import BaseCommand

from blog.images import to_webp
from blog.models import Blog


class Command(BaseCommand):
    help = "Convert existing blog featured images to resized WebP. Original files are kept on disk."

    def handle(self, *args, **options):
        for blog in Blog.objects.exclude(featured_image=""):
            image = blog.featured_image
            if image.name.lower().endswith(".webp"):
                continue
            try:
                old_size = image.size
                webp = to_webp(image)
                image.close()
                image.save(Path(webp.name).name, webp, save=True)
                self.stdout.write(f"{blog.slug}: {old_size // 1024} KB -> {image.size // 1024} KB")
            except Exception as exc:
                self.stderr.write(f"{blog.slug}: skipped ({exc})")
