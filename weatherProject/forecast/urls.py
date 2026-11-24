from django.urls import path
from . import views

urlpatterns = [
    path('', views.forecast_page, name='forecast'),
    path('api/now/', views.now_api, name='now_api'),
    path('api/forecast/', views.forecast_api, name='forecast_api'),
    path('sw.js', views.service_worker, name='sw'),
    path('manifest.webmanifest', views.web_manifest, name='manifest'),
    path('api/island/', views.island_api, name='island_api'),
    path('api/scorecard/', views.scorecard_api, name='scorecard_api'),
    path('api/search/', views.search_api, name='search_api'),
    path('classic/', views.weather_view, name='classic'),
    path('healthz/', views.healthz, name='healthz'),
    path('auto-location/', views.auto_location, name='auto_location'),
]