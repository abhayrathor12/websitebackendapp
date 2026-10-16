from django.http import HttpResponse
from django.utils.html import escape
from django.views.decorators.cache import cache_page

from .models import Blog

SITE_URL = "https://www.technovizautomation.com"

# Pages of the React website. When you add a new page, service or product
# to the frontend, add its path here so Google finds it.
STATIC_PAGES = [
    ("/", "weekly", "1.0"),
    ("/services", "monthly", "0.9"),
    ("/products", "monthly", "0.9"),
    ("/blogs", "weekly", "0.9"),
    ("/case-studies", "monthly", "0.7"),
    ("/company", "monthly", "0.7"),
    ("/contact", "yearly", "0.7"),
    ("/coe", "monthly", "0.6"),
    ("/learning", "monthly", "0.6"),
    ("/book", "monthly", "0.5"),
    ("/python", "monthly", "0.5"),
    ("/react", "monthly", "0.5"),
    ("/azure", "monthly", "0.5"),
    ("/network", "monthly", "0.5"),
    ("/mysql", "monthly", "0.5"),
    ("/android", "monthly", "0.5"),
    ("/Smart-Manufacturing-AI-Masterclass", "monthly", "0.5"),
    ("/Webinar-Registration", "monthly", "0.4"),
    ("/Ideathon", "monthly", "0.4"),
]

SERVICE_SLUGS = [
    "digitization",
    "iiot",
    "industrial-communication",
    "cybersecurity",
    "automation-services",
    "ai-manufacturing",
    "smart-industry-readiness-index",
]

PRODUCT_SLUGS = [
    "immersix",
    "utility360",
    "digital-checksheet",
    "smart-ems",
    "oee-dashboard",
    "vision-ai",
]

# Older posts that live in the frontend code (src/data/mockData.ts), not in the database
FRONTEND_BLOG_SLUGS = [
    "industrial-communication-skills",
    "industrial-iot-business-models",
    "boost-productivity-with-oeedashboard",
    "smart-alarm-management-scada",
    "iiot-amplified-lighting-control",
    "energy-management-system-efficiency",
    "challenges-in-industry-4-0",
    "transformation-industry-3-to-4",
    "industry-4-0",
    "future-of-iiot-in-india",
]


def _url(path, lastmod=None, changefreq=None, priority=None):
    parts = [f"<loc>{escape(SITE_URL + path)}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod.isoformat()}</lastmod>")
    if changefreq:
        parts.append(f"<changefreq>{changefreq}</changefreq>")
    if priority:
        parts.append(f"<priority>{priority}</priority>")
    return "  <url>" + "".join(parts) + "</url>"


@cache_page(60 * 60)
def sitemap_xml(request):
    entries = [_url(path, changefreq=freq, priority=prio) for path, freq, prio in STATIC_PAGES]
    entries += [_url(f"/services/{slug}", changefreq="monthly", priority="0.8") for slug in SERVICE_SLUGS]
    entries += [_url(f"/products/{slug}", changefreq="monthly", priority="0.8") for slug in PRODUCT_SLUGS]
    for blog in Blog.objects.order_by("-publish_date").only("slug", "publish_date"):
        entries.append(_url(f"/blogs/{blog.slug}", lastmod=blog.publish_date, priority="0.7"))
    entries += [_url(f"/blogs/{slug}", priority="0.5") for slug in FRONTEND_BLOG_SLUGS]

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    return HttpResponse(xml, content_type="application/xml")
