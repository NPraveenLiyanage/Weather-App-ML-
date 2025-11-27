from django.urls import path
from . import views

urlpatterns = [
    path('',views.weather_view, name='Weather View'),
    path('healthz/', views.healthz, name='healthz'),
    path('auto-location/', views.auto_location, name='auto_location'),
]