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
