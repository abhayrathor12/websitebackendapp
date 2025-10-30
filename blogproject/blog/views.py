from django.shortcuts import render
from django.core.mail import send_mail,BadHeaderError
from rest_framework import viewsets
from .models import Blog,Contact
from .serializers import BlogSerializer,ContactSerializer
from django.shortcuts import render, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404




class BlogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Blog.objects.all().order_by('-publish_date')
    serializer_class = BlogSerializer

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

class ContactViewSet(viewsets.ModelViewSet):  # allow POST
    queryset = Contact.objects.all().order_by('-created_at')
    serializer_class = ContactSerializer
    

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

        return redirect("add_blog")  

    return render(request, "blog.html")



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

def contact_list(request):
    contacts = Contact.objects.all().order_by("-id")  # latest first
    return render(request, "contact_list.html", {"contacts": contacts})

def blog_list(request):
    blogs = Blog.objects.all().order_by("-publish_date")
    return render(request, "blog_list.html", {"blogs": blogs})
