from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView


def salud(request):
    return HttpResponse("ok")


admin.site.site_header = "notificación"
admin.site.site_title = "notificación"
admin.site.index_title = "Administración"

urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", admin.site.urls),
    path("whatsapp/", include("apps.whatsapp.urls")),
    path("salud/", salud),
]
