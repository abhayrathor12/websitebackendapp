from rest_framework import serializers

from .models import Question


class AdminQuestionSerializer(serializers.ModelSerializer):
    """Full question including the correct option — staff only."""

    class Meta:
        model = Question
        fields = [
            "id", "text", "option_a", "option_b", "option_c", "option_d",
            "correct_option", "order",
        ]
        read_only_fields = ["id", "order"]

    def validate(self, attrs):
        for field in ["text", "option_a", "option_b", "option_c", "option_d"]:
            if field in attrs:
                attrs[field] = attrs[field].strip()
                if not attrs[field]:
                    label = "Question" if field == "text" else f"Option {field[-1].upper()}"
                    raise serializers.ValidationError({field: f"{label} cannot be empty."})
        return attrs
