from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('stats/', views.stats, name='stats'),
    path('download/<int:pk>/', views.download_txt, name='download'),
    path('export/', views.export_csv, name='export'),
]