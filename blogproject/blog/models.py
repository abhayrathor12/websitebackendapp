from django.db import models

from .images import to_webp


class Blog(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    author = models.CharField(max_length=100)
    excerpt = models.TextField()
    body = models.TextField()
    tags = models.CharField(max_length=200)  # comma-separated
    featured_image = models.ImageField(upload_to='blog_images/')
    publish_date = models.DateField()
    seo_meta_title = models.CharField(max_length=200)
    seo_description = models.TextField()

    def save(self, *args, **kwargs):
        # A newly uploaded image is converted to a smaller WebP before it is stored
        image = self.featured_image
        if image and not image._committed:
            try:
                self.featured_image = to_webp(image)
            except Exception as exc:
                print("Could not optimize blog image, keeping the original:", exc)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title



class Contact(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    company = models.CharField(max_length=200, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    timeline = models.CharField(max_length=50, blank=True, null=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"


class WebinarRegistration(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    company_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=15)

    city = models.CharField(max_length=100,null=True,blank=True)  # ✅ NEW
    attended = models.BooleanField(default=False)  # ✅ NEW

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.email}"

from django.db import models


class IdeathonRegistration(models.Model):
    PARTICIPATION_CHOICES = (
        ("Individual", "Individual"),
        ("Team", "Team"),
    )

    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)

    participation_type = models.CharField(
        max_length=20,
        choices=PARTICIPATION_CHOICES
    )

    team_name = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    idea_title = models.CharField(max_length=255)

    # Store ["AI/ML","IIoT"]
    focus_areas = models.JSONField(default=list)

    idea_description = models.TextField()

    pitch_deck = models.FileField(
        upload_to="pitch_decks/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name
    
    
from django.db import models


class MasterClassRegistration(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=15)

    payment_id = models.CharField(max_length=100, unique=True)
    order_id = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=99.00)  # in rupees

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.email} ({self.payment_id})"