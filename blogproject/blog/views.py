import threading

from django.shortcuts import render
from django.core.mail import send_mail,BadHeaderError
from rest_framework import viewsets
from .models import Blog,Contact,WebinarRegistration
from .serializers import BlogSerializer,ContactSerializer
from django.shortcuts import render, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from rest_framework.permissions import AllowAny, IsAdminUser


class PublicPostAdminGet:
    """Anyone can submit (POST); only logged-in staff can read the list (GET)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAdminUser()]




class BlogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Blog.objects.all().order_by('-publish_date')
    serializer_class = BlogSerializer
    lookup_field = 'slug'

def send_contact_emails(contact):
    """Thank-you mail to the visitor + notification to the team. Runs in a background
    thread so the contact form gets its response straight away."""
    try:
        send_mail(
            subject="Thanks for contacting Technoviz Automation",
            message=(
                f"Hello {contact.name},\n\n"
                f"Thank you for reaching out to us! "
                f"We have received your message and will get back to you soon.\n\n"
                f"Your Message: {contact.message}\n\n"
                "Best regards,\nTechnoviz Automation"
            ),
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[contact.email],
            fail_silently=False,
        )
        send_mail(
            subject=f"📩 New Contact Form Submission from {contact.name}",
            message=(
                f"A new contact form has been submitted.\n\n"
                f"Name: {contact.name}\n"
                f"Email: {contact.email}\n"
                f"Company: {contact.company or 'N/A'}\n"
                f"Phone: {contact.phone or 'N/A'}\n"
                f"Timeline: {contact.timeline or 'N/A'}\n\n"
                f"Message:\n{contact.message}\n\n"
                f"Submitted at: {contact.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=["rathorabhay633@gmail.com"],
            fail_silently=False,
        )
    except BadHeaderError:
        print("❌ Bad header found while sending contact email")
    except Exception as e:
        print("❌ Error sending contact mail:", str(e))


class ContactCreateView(APIView):
    def post(self, request):
        serializer = ContactSerializer(data=request.data)
        if serializer.is_valid():
            contact = serializer.save()

            # Emails go out in the background; the website gets its answer right away
            threading.Thread(target=send_contact_emails, args=(contact,), daemon=True).start()

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ContactViewSet(viewsets.ModelViewSet):
    # Not used by the website (it posts to con/create/); admin-only so leads stay private
    permission_classes = [IsAdminUser]
    queryset = Contact.objects.all().order_by('-created_at')
    serializer_class = ContactSerializer
    

@staff_member_required
def add_blog(request):
    if request.method == "POST":
        title = request.POST.get("title")
        slug = request.POST.get("slug")
        author = request.POST.get("author")
        excerpt = request.POST.get("excerpt")
        body = request.POST.get("body")
        tags = request.POST.get("tags")
        publish_date = request.POST.get("publish_date")
        seo_meta_title = request.POST.get("seo_meta_title")
        seo_description = request.POST.get("seo_description")
        featured_image = request.FILES.get("featured_image")

        Blog.objects.create(
            title=title,
            slug=slug,
            author=author,
            excerpt=excerpt,
            body=body,
            tags=tags,
            publish_date=publish_date,
            seo_meta_title=seo_meta_title,
            seo_description=seo_description,
            featured_image=featured_image
        )

        return redirect("/blogpage/?success=1") 

    return render(request, "blog.html")



@staff_member_required
def edit_blog(request, blog_id):
    blog = get_object_or_404(Blog, id=blog_id)

    if request.method == "POST":
        blog.title = request.POST.get("title")
        blog.slug = request.POST.get("slug")
        blog.author = request.POST.get("author")
        blog.excerpt = request.POST.get("excerpt")
        blog.body = request.POST.get("body")
        blog.tags = request.POST.get("tags")
        blog.publish_date = request.POST.get("publish_date")
        blog.seo_meta_title = request.POST.get("seo_meta_title")
        blog.seo_description = request.POST.get("seo_description")

        if request.FILES.get("featured_image"):
            blog.featured_image = request.FILES.get("featured_image")

        blog.save()
        return redirect("blog_list")

    return render(request, "edit.html", {"blog": blog})

@staff_member_required
def contact_list(request):
    contacts = Contact.objects.all().order_by("-id")  # latest first
    return render(request, "contact_list.html", {"contacts": contacts})


@staff_member_required
def delete_contact(request, pk):
    """Delete one contact form submission (POST only, from the View Contacts page)."""
    if request.method == "POST":
        Contact.objects.filter(pk=pk).delete()
    return redirect("contact_list")


@staff_member_required
def delete_multiple_contacts(request):
    """Delete the ticked contact submissions (POST only, from the View Contacts page)."""
    if request.method == "POST":
        ids = [i for i in request.POST.getlist("ids") if i.isdigit()]
        if ids:
            Contact.objects.filter(pk__in=ids).delete()
    return redirect("contact_list")

@staff_member_required
def blog_list(request):
    blogs = Blog.objects.all().order_by("-publish_date")
    return render(request, "blog_list.html", {"blogs": blogs})

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

@staff_member_required
def delete_blog(request, blog_id):
    blog = get_object_or_404(Blog, id=blog_id)

    if request.method == "POST":
        blog.delete()
        messages.success(request, "Blog deleted successfully.")
        return redirect("blog_list")

    return redirect("blog_list")

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import WebinarRegistration
from .serializers import WebinarRegistrationSerializer

import threading
from django.core.mail import send_mail, BadHeaderError

from sib_api_v3_sdk import ApiClient, Configuration
from sib_api_v3_sdk.api.transactional_emails_api import TransactionalEmailsApi
from sib_api_v3_sdk.models import SendSmtpEmail
import os

def send_webinar_emails(registration):
    try:
       
        send_mail(
            subject=f"📩 New Webinar Registration: {registration.first_name}",
            message=(
                f"Name: {registration.first_name} {registration.last_name}\n"
                f"Company: {registration.company_name}\n"
                f"Email: {registration.email}\n"
                f"Phone: {registration.phone}\n"
                f"Registered at: {registration.created_at}"
            ),
            from_email=None,
            recipient_list=["kkhurana@technovizautomation.com"],
            fail_silently=False,
        )

    except BadHeaderError:
        print("❌ Bad header in webinar email")
    except Exception as e:
        print("❌ Email sending failed:", str(e))



class WebinarRegistrationAPIView(PublicPostAdminGet, APIView):

    def post(self, request):
        serializer = WebinarRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            registration = serializer.save()

            # ✅ Send email in background (PythonAnywhere safe)
            threading.Thread(
                target=send_webinar_emails,
                args=(registration,),
                daemon=True
            ).start()

            # ✅ Instant response → popup shows immediately
            return Response(
                {"message": "Registration successful"},
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def get(self, request):
        registrations = WebinarRegistration.objects.all().order_by("-created_at")
        serializer = WebinarRegistrationSerializer(registrations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

@staff_member_required
def webinar_list(request):
    Webinar = WebinarRegistration.objects.all().order_by("-id")  # latest first
    return render(request, "webinar_contact.html", {"registrations": Webinar})

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

@staff_member_required
@require_POST
def delete_webinar(request, pk):
    WebinarRegistration.objects.filter(id=pk).delete()
    return JsonResponse({"status": "ok"})

@staff_member_required
@require_POST
def delete_multiple_webinar(request):
    data = json.loads(request.body)
    WebinarRegistration.objects.filter(id__in=data["ids"]).delete()
    return JsonResponse({"status": "ok"})

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
import json

@staff_member_required
@require_POST
def toggle_attended(request, pk):
    if request.method == "POST":
        reg = get_object_or_404(WebinarRegistration, pk=pk)
        data = json.loads(request.body)
        reg.attended = data.get("attended", False)
        reg.save()
        return JsonResponse({"success": True, "attended": reg.attended})
    
    
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IdeathonRegistration
from .serializers import IdeathonRegistrationSerializer


class IdeathonRegistrationAPIView(PublicPostAdminGet, APIView):

    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        registrations = IdeathonRegistration.objects.all().order_by("-created_at")
        serializer = IdeathonRegistrationSerializer(registrations, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = IdeathonRegistrationSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "Registration successful.",
                    "data": serializer.data
                },
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
        
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json


@staff_member_required
def ideathon_list(request):
    registrations = IdeathonRegistration.objects.all().order_by("-id")
    return render(request, "ideathon_list.html", {"registrations": registrations})


@staff_member_required
@require_POST
def delete_ideathon(request, pk):
    IdeathonRegistration.objects.filter(id=pk).delete()
    return JsonResponse({"status": "ok"})


@staff_member_required
@require_POST
def delete_multiple_ideathon(request):
    data = json.loads(request.body)
    IdeathonRegistration.objects.filter(id__in=data["ids"]).delete()
    return JsonResponse({"status": "ok"})

from rest_framework.views import APIView
from rest_framework.response import Response
import razorpay
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response

from django.conf import settings

from .models import MasterClassRegistration
from .serializers import MasterClassRegistrationSerializer

from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
import razorpay
from django.conf import settings

from .models import MasterClassRegistration
from .serializers import MasterClassRegistrationSerializer

client = razorpay.Client(auth=(
    settings.RAZORPAY_KEY_ID,
    settings.RAZORPAY_KEY_SECRET
))


MASTERCLASS_NAME = "Smart Manufacturing & AI Masterclass 2026"
# Logo on a white tile, embedded inside the email (cid:) so it always shows,
# also when the mail app blocks outside images, and stays visible in dark mode.
EMAIL_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_assets", "logo_tile.png")
EMAIL_LOGO_CID = "technoviz-logo"
SITE_URL = "https://technovizautomation.com"
SUPPORT_EMAIL = "support@technovizautomation.com"


def attach_inline_logo(message):
    """Embed the logo so the HTML can show it with src="cid:technoviz-logo"."""
    from email.mime.image import MIMEImage

    with open(EMAIL_LOGO_PATH, "rb") as f:
        logo = MIMEImage(f.read(), _subtype="png")
    logo.add_header("Content-ID", f"<{EMAIL_LOGO_CID}>")
    logo.add_header("Content-Disposition", "inline", filename="technoviz-logo.png")
    message.mixed_subtype = "related"  # image belongs to the HTML, not a separate attachment
    message.attach(logo)


def send_masterclass_emails(registration):
    """Mail 1: welcome to the Technoviz family + registration confirmation
    (designed HTML, with a plain-text version for clients that block HTML)."""
    from zoneinfo import ZoneInfo

    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils import timezone as dj_timezone

    try:
        first_name = (registration.name or "").strip().split(" ")[0] or "there"
        registered_at = dj_timezone.localtime(
            registration.created_at, ZoneInfo("Asia/Kolkata")
        ).strftime("%d %b %Y, %I:%M %p (IST)")
        amount = f"{registration.amount:,.2f}"
        details = [
            ("Name", registration.name),
            ("Email", registration.email),
            ("Phone", registration.phone),
            ("Payment ID", registration.payment_id),
            ("Order ID", registration.order_id),
            ("Registered on", registered_at),
        ]
        steps = [
            ("Masterclass joining link",
             "You'll receive a separate email with your masterclass date, time and joining link."),
            ("Master Portal access",
             "We'll email your Master Portal login. Watch the welcome video there and take the "
             "Pre Assessment once your masterclass starts."),
            ("Your certificate",
             "After the masterclass, download your certificate from the portal and share it on LinkedIn."),
        ]

        html = render_to_string("emails/masterclass_welcome.html", {
            "name": registration.name,
            "first_name": first_name,
            "masterclass_name": MASTERCLASS_NAME,
            "details": details,
            "amount": amount,
            "steps": steps,
            "logo_src": f"cid:{EMAIL_LOGO_CID}",
            "site_url": SITE_URL,
            "support_email": SUPPORT_EMAIL,
            "year": dj_timezone.now().year,
        })

        text = (
            f"Hi {registration.name},\n\n"
            f"Welcome to the Technoviz family! Your payment was successful and your seat for the "
            f"{MASTERCLASS_NAME} is confirmed.\n\n"
            f"Registration details:\n"
            + "".join(f"{label}: {value}\n" for label, value in details)
            + f"Amount Paid: ₹{amount}\n\n"
            f"What happens next?\n"
            + "".join(f"{i}. {title}: {body}\n" for i, (title, body) in enumerate(steps, 1))
            + f"\nQuestions? Write to us at {SUPPORT_EMAIL}\n\n"
            f"See you at the masterclass!\n"
            f"Team Technoviz Automation"
        )

        message = EmailMultiAlternatives(
            subject=f"Welcome to the Technoviz Family, {first_name}! Your registration is confirmed 🎉",
            body=text,
            from_email=None,
            to=[registration.email],
        )
        message.attach_alternative(html, "text/html")
        attach_inline_logo(message)
        message.send(fail_silently=False)

    except BadHeaderError:
        print("❌ Bad header in masterclass email")
    except Exception as e:
        print("❌ Email sending failed:", str(e))


def masterclass_after_payment(registration):
    """Mail 1: confirmation (unchanged). Then mail 2: meeting link of the next
    webinar and mail 3: Master Portal link (webinar_schedule app)."""
    from django.db import close_old_connections
    from webinar_schedule.services import handle_new_registration

    send_masterclass_emails(registration)
    try:
        handle_new_registration(registration)
    except Exception as e:
        print("❌ Webinar/portal emails failed:", str(e))
    finally:
        close_old_connections()


class TestRegisterView(APIView):
    """TESTING ONLY: registers without Razorpay so the emails can be tested.
    Works only when MASTERCLASS_SKIP_PAYMENT=1 is set in the backend environment;
    otherwise it returns 404 (production is not affected)."""

    def post(self, request):
        if not getattr(settings, "MASTERCLASS_SKIP_PAYMENT", False):
            return Response({"success": False, "message": "Not found"}, status=404)

        import uuid
        serializer = MasterClassRegistrationSerializer(data=request.data.get("registration_data", {}))
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=400)

        registration = serializer.save(
            payment_id=f"TEST-{uuid.uuid4().hex[:12]}",
            order_id="TEST-NO-PAYMENT",
            amount=Decimal("0"),
        )
        threading.Thread(target=masterclass_after_payment, args=(registration,), daemon=True).start()
        return Response({"success": True, "message": "Test registration saved (no payment)"})


class CreateOrderView(APIView):

    def post(self, request):
        amount = 584982  # in paise

        order = client.order.create({
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1
        })

        return Response({
            "order_id": order["id"],
            "amount": amount,
            "key": settings.RAZORPAY_KEY_ID
        })


class VerifyPaymentView(APIView):

    def post(self, request):
        data = request.data

        params_dict = {
            "razorpay_order_id": data.get("razorpay_order_id"),
            "razorpay_payment_id": data.get("razorpay_payment_id"),
            "razorpay_signature": data.get("razorpay_signature"),
        }

        try:
            client.utility.verify_payment_signature(params_dict)

            payment_id = data.get("razorpay_payment_id")

            if MasterClassRegistration.objects.filter(payment_id=payment_id).exists():
                return Response({
                    "success": True,
                    "message": "Registration already recorded"
                })

            # Fetch the actual captured payment from Razorpay - source of truth for amount
            payment = client.payment.fetch(payment_id)
            actual_amount_rupees = Decimal(payment["amount"]) / Decimal(100)

            registration_data = data.get("registration_data", {})
            serializer = MasterClassRegistrationSerializer(data=registration_data)

            if serializer.is_valid():
                registration = serializer.save(
                    payment_id=payment_id,
                    order_id=data.get("razorpay_order_id"),
                    amount=actual_amount_rupees,
                )

                # ✅ Send email in background (PythonAnywhere safe)
                threading.Thread(
                    target=masterclass_after_payment,
                    args=(registration,),
                    daemon=True
                ).start()

                return Response({
                    "success": True,
                    "message": "Payment verified & registration saved"
                })

            return Response({
                "success": False,
                "errors": serializer.errors
            }, status=400)

        except razorpay.errors.SignatureVerificationError:
            return Response({
                "success": False,
                "message": "Payment signature verification failed"
            }, status=400)

        except Exception as e:
            return Response({
                "success": False,
                "message": str(e)
            }, status=400)
            
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from .models import MasterClassRegistration


@staff_member_required
def masterclass_list(request):
    registrations = MasterClassRegistration.objects.all().order_by("-id")
    return render(request, "masterclass_list.html", {"registrations": registrations})


@staff_member_required
@require_POST
def delete_masterclass(request, pk):
    MasterClassRegistration.objects.filter(id=pk).delete()
    return JsonResponse({"status": "ok"})


@staff_member_required
@require_POST
def delete_multiple_masterclass(request):
    data = json.loads(request.body)
    MasterClassRegistration.objects.filter(id__in=data["ids"]).delete()
    return JsonResponse({"status": "ok"})
