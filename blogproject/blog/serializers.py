from rest_framework import serializers
from .models import Blog,Contact, MasterClassRegistration

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
        
        
import json

from rest_framework import serializers
from .models import IdeathonRegistration


class IdeathonRegistrationSerializer(serializers.ModelSerializer):

    class Meta:
        model = IdeathonRegistration
        fields = "__all__"

    def validate_focus_areas(self, value):
        """
        React is sending:
        JSON.stringify(form.focusAreas)

        Convert string -> list
        """

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                raise serializers.ValidationError(
                    "Invalid focus areas."
                )

        return value
    
    
# serializers.py

from rest_framework import serializers
from .models import MasterClassRegistration


class MasterClassRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterClassRegistration
        fields = ["id", "name", "email", "phone", "payment_id", "order_id", "amount", "created_at"]
        read_only_fields = ["id", "payment_id", "order_id", "amount", "created_at"]