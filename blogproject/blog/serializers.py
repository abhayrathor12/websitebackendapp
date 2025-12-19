from rest_framework import serializers
from .models import Blog,Contact

class BlogSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    
    class Meta:
        model = Blog
        fields = '__all__'
    
    def get_tags(self, obj):
        return obj.tags.split(',')


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'
        
from rest_framework import serializers
from .models import WebinarRegistration

class WebinarRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebinarRegistration
        fields = "__all__"