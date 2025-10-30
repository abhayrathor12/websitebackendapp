from django import forms
from .models import Blog

class BlogForm(forms.ModelForm):
    class Meta:
        model = Blog
        fields = [
            'title', 'slug', 'author', 'excerpt', 'body',
            'tags', 'featured_image', 'publish_date',
            'seo_meta_title', 'seo_description'
        ]
        widgets = {
            'publish_date': forms.DateInput(attrs={'type': 'date'}),
            'tags': forms.TextInput(attrs={'placeholder': 'Comma separated tags'}),
        }
