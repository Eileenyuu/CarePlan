from django.urls import path
from . import views

urlpatterns = [
    # ===== 页面路由（返回 HTML）=====
    path('', views.index, name='index'),
    path('result/<int:pk>/', views.result, name='result'),
    path('stats/', views.stats, name='stats'),
    
    # ===== API 路由（返回 JSON）=====
    path('api/careplans/<int:pk>/status/', views.get_careplan_status, name='careplan_status'),
    
    # ===== 下载路由 =====
    path('download/<int:pk>/', views.download_txt, name='download'),
    path('export/', views.export_csv, name='export'),
]