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

class ContactCreateView(APIView):
    def post(self, request):
        serializer = ContactSerializer(data=request.data)
        if serializer.is_valid():
            contact = serializer.save()

            print("📩 Preparing to send mail to:", contact.email)

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
                    recipient_list=["rathorabhay633@gmail.com"],  # <-- your email here
                    fail_silently=False,
                )

            except BadHeaderError:
                print("❌ Bad header found while sending email")
            except Exception as e:
                print("❌ Error sending mail:", str(e))

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
                serializer.save(
                    payment_id=payment_id,
                    order_id=data.get("razorpay_order_id"),
                    amount=actual_amount_rupees,
                )
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
