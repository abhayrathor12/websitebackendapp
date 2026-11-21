"""Portal accounts are created automatically when someone pays for the Masterclass."""

import re
import secrets

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from .models import PortalProfile

User = get_user_model()


def generate_password(name):
    """First name + @ + 4 random digits, e.g. 'Rahul@4821'."""
    words = (name or "").split()
    first = re.sub(r"[^A-Za-z]", "", words[0] if words else "")[:12] or "User"
    return f"{first.capitalize()}@{secrets.randbelow(10000):04d}"


def find_account(email):
    email = (email or "").strip()
    return (
        User.objects.filter(username__iexact=email).first()
        or User.objects.filter(email__iexact=email).first()
    )


def ensure_portal_account(name, email):
    """Returns (user, password). password is None when the account already
    existed (they keep their existing password)."""
    email = (email or "").strip().lower()
    name = (name or "").strip() or email

    user = find_account(email)
    if user:
        if not user.is_staff and not hasattr(user, "portal_profile"):
            PortalProfile.objects.create(user=user, full_name=name)
        return user, None

    password = generate_password(name)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name[:150],
                is_active=True,  # can log in straight away
            )
            PortalProfile.objects.create(user=user, full_name=name)
    except IntegrityError:  # created at the same moment by another request
        return find_account(email), None
    return user, password


def new_password_if_never_used(user):
    """For resending the portal mail: the original password was never seen
    (mail failed), so issue a new one - only if they never logged in."""
    if user.is_staff or user.last_login is not None:
        return None
    full_name = getattr(getattr(user, "portal_profile", None), "full_name", "") or user.first_name
    password = generate_password(full_name)
    user.set_password(password)
    user.save(update_fields=["password"])
    return password
