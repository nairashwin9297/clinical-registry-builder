from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.config),
    path("notes/", views.notes_list),
    path("notes/upload/", views.upload_notes),
    path("notes/<int:pk>/", views.note_detail),
    path("notes/<int:pk>/extract/", views.run_extraction),
    path("extractions/", views.extractions_list),
    path("extractions/<int:pk>/review/", views.submit_review),
    path("review-queue/", views.review_queue),
    path("metrics/", views.metrics),
    path("export/registry.csv", views.export_registry),
    path("export/redcap.csv", views.export_redcap),
    path("export/redcap-dictionary.csv", views.export_redcap_dictionary),
    path("live/status/", views.live_status),
]
