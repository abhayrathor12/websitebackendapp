from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import MasterClassRegistration

FORM = {
    "name": "Test User",
    "email": "test@example.com",
    "phone": "9876543210",
    "company_email": "test@company.com",
    "pin_code": "110001",
    "company_name": "Test Co",
}


@mock.patch("blog.views.threading.Thread")  # no emails / Zoho calls in tests
class MasterclassRegistrationTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def post(self, data):
        return self.api.post("/api/test-register/", {"registration_data": data}, format="json")

    @override_settings(MASTERCLASS_SKIP_PAYMENT=True)
    def test_saves_optional_fields(self, _thread):
        res = self.post(FORM)
        self.assertEqual(res.status_code, 200, res.content)
        reg = MasterClassRegistration.objects.get()
        self.assertEqual(
            (reg.company_email, reg.pin_code, reg.company_name),
            ("test@company.com", "110001", "Test Co"),
        )

    @override_settings(MASTERCLASS_SKIP_PAYMENT=True)
    def test_optional_fields_can_be_blank(self, _thread):
        data = {k: FORM[k] for k in ("name", "email", "phone")}
        data.update(company_email="", pin_code="", company_name="")
        self.assertEqual(self.post(data).status_code, 200)
        reg = MasterClassRegistration.objects.get()
        self.assertEqual((reg.company_email, reg.pin_code, reg.company_name), ("", "", ""))

    @override_settings(MASTERCLASS_SKIP_PAYMENT=True)
    def test_bad_pin_code_rejected(self, _thread):
        self.assertEqual(self.post({**FORM, "pin_code": "12ab"}).status_code, 400)
        self.assertFalse(MasterClassRegistration.objects.exists())

    @override_settings(MASTERCLASS_SKIP_PAYMENT=False)
    def test_test_register_disabled_without_flag(self, _thread):
        self.assertEqual(self.post(FORM).status_code, 404)
        self.assertFalse(MasterClassRegistration.objects.exists())
