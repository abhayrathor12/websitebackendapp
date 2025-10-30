from django.db import models

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
