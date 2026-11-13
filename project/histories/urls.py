from django.urls import path
from . import api, views

app_name = "histories"
urlpatterns = [
    path("", views.home, name="home"),
    path("research/<slug:slug>/", views.card_detail, name="card"),
    path("records/", views.records, name="records"),
    path("records/<int:pk>/", views.record_detail, name="record"),
    path("api/records/", api.RecordsAPI.as_view(), name="api-records"),
    path("api/records/<int:pk>/", api.RecordAPI.as_view(), name="api-record"),
    path("api/research/", api.ResearchAPI.as_view(), name="api-research"),
    path("api/research/<slug:slug>/", api.ResearchDetailAPI.as_view(), name="api-card"),
]
