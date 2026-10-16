from django.conf import settings
from django.http import HttpResponse
from django.urls import include, path


def frontend_missing(request):
    # WhiteNoise serves frontend/dist/index.html at "/" when the frontend has been built.
    # Reaching this view means it hasn't been, so say how to fix that.
    return HttpResponse(
        f"The frontend isn't built ({settings.FRONTEND_DIST} not found). Run `npm run build` in frontend/, "
        "or use the Vite dev server (npm run dev). The API is at /api/.",
        content_type="text/plain", status=404)


urlpatterns = [
    path("api/", include("registry.urls")),
    path("", frontend_missing),
]
