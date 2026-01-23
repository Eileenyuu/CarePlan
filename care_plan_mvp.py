# ============================================
# 1. requirements.txt
# ============================================
"""
Django==4.2
anthropic==0.18.1
python-dotenv==1.0.0
"""

# ============================================
# 2. Dockerfile
# ============================================
"""
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD python manage.py migrate && python manage.py runserver 0.0.0.0:8000
"""

# ============================================
# 3. docker-compose.yml
# ============================================
"""
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - .:/app
"""

# ============================================
# 4. .env (需要你自己创建)
# ============================================
"""
ANTHROPIC_API_KEY=your_api_key_here
"""

# ============================================
# 5. careplan/settings.py
# ============================================
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'dev-secret-key-change-in-production'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'careplan.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
    ]},
}]

WSGI_APPLICATION = 'careplan.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
"""

# ============================================
# 6. careplan/urls.py
# ============================================
"""
from django.urls import path, include

urlpatterns = [
    path('', include('app.urls')),
]
"""

# ============================================
# 7. careplan/wsgi.py
# ============================================
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'careplan.settings')
application = get_wsgi_application()
"""

# ============================================
# 8. app/models.py
# ============================================
"""
from django.db import models

class CarePlan(models.Model):
    patient_first_name = models.CharField(max_length=100)
    patient_last_name = models.CharField(max_length=100)
    patient_dob = models.DateField()
    patient_mrn = models.CharField(max_length=6)
    referring_provider = models.CharField(max_length=200)
    referring_provider_npi = models.CharField(max_length=10)
    medication_name = models.CharField(max_length=200)
    patient_primary_diagnosis = models.CharField(max_length=20)
    additional_diagnosis = models.TextField(blank=True)
    medication_history = models.TextField(blank=True)
    clinical_notes = models.TextField(blank=True)
    
    generated_plan = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
"""

# ============================================
# 9. app/views.py
# ============================================
"""
import os
import csv
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from anthropic import Anthropic
from .models import CarePlan

def index(request):
    if request.method == 'POST':
        cp = CarePlan.objects.create(
            patient_first_name=request.POST['patient_first_name'],
            patient_last_name=request.POST['patient_last_name'],
            patient_dob=request.POST['patient_dob'],
            patient_mrn=request.POST['patient_mrn'],
            referring_provider=request.POST['referring_provider'],
            referring_provider_npi=request.POST['referring_provider_npi'],
            medication_name=request.POST['medication_name'],
            patient_primary_diagnosis=request.POST['patient_primary_diagnosis'],
            additional_diagnosis=request.POST.get('additional_diagnosis', ''),
            medication_history=request.POST.get('medication_history', ''),
            clinical_notes=request.POST.get('clinical_notes', ''),
        )
        
        # 调用 Claude 生成 Care Plan
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
        prompt = f'''Generate a comprehensive Specialty Pharmacy Care Plan for:

Patient: {cp.patient_first_name} {cp.patient_last_name}
DOB: {cp.patient_dob}
MRN: {cp.patient_mrn}
Medication: {cp.medication_name}
Primary Diagnosis (ICD-10): {cp.patient_primary_diagnosis}
Additional Diagnoses: {cp.additional_diagnosis}
Medication History: {cp.medication_history}
Clinical Notes: {cp.clinical_notes}

Please include:
1. Problem List / Drug Therapy Problems (DTPs)
2. SMART Goals
3. Pharmacist Interventions/Plan
4. Monitoring Plan & Lab Schedule
'''
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        cp.generated_plan = response.content[0].text
        cp.save()
        
        return render(request, 'result.html', {'care_plan': cp})
    
    return render(request, 'form.html')

def download_txt(request, pk):
    cp = get_object_or_404(CarePlan, pk=pk)
    response = HttpResponse(cp.generated_plan, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="careplan_{cp.patient_mrn}.txt"'
    return response

def export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="careplans.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Patient First Name', 'Patient Last Name', 'DOB', 'MRN',
        'Provider', 'Provider NPI', 'Medication', 'Primary Diagnosis',
        'Additional Diagnosis', 'Medication History', 'Created At'
    ])
    
    for cp in CarePlan.objects.all():
        writer.writerow([
            cp.patient_first_name, cp.patient_last_name, cp.patient_dob, cp.patient_mrn,
            cp.referring_provider, cp.referring_provider_npi, cp.medication_name,
            cp.patient_primary_diagnosis, cp.additional_diagnosis, cp.medication_history,
            cp.created_at
        ])
    
    return response
"""

# ============================================
# 10. app/urls.py
# ============================================
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('download/<int:pk>/', views.download_txt, name='download'),
    path('export/', views.export_csv, name='export'),
]
"""

# ============================================
# 11. app/templates/form.html
# ============================================
"""
<!DOCTYPE html>
<html>
<head>
    <title>Care Plan Generator</title>
    <style>
        body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }
        input, textarea { width: 100%; padding: 8px; margin: 5px 0 15px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
        button:hover { background: #0056b3; }
        label { font-weight: bold; }
    </style>
</head>
<body>
    <h1>Specialty Pharmacy Care Plan Generator</h1>
    <form method="post">
        <label>Patient First Name *</label>
        <input type="text" name="patient_first_name" required>
        
        <label>Patient Last Name *</label>
        <input type="text" name="patient_last_name" required>
        
        <label>Patient DOB *</label>
        <input type="date" name="patient_dob" required>
        
        <label>Patient MRN (6 digits) *</label>
        <input type="text" name="patient_mrn" required>
        
        <label>Referring Provider *</label>
        <input type="text" name="referring_provider" required>
        
        <label>Referring Provider NPI (10 digits) *</label>
        <input type="text" name="referring_provider_npi" required>
        
        <label>Medication Name *</label>
        <input type="text" name="medication_name" required>
        
        <label>Patient Primary Diagnosis (ICD-10) *</label>
        <input type="text" name="patient_primary_diagnosis" required>
        
        <label>Additional Diagnosis (comma separated)</label>
        <textarea name="additional_diagnosis" rows="2"></textarea>
        
        <label>Medication History (comma separated)</label>
        <textarea name="medication_history" rows="3"></textarea>
        
        <label>Clinical Notes</label>
        <textarea name="clinical_notes" rows="5"></textarea>
        
        <button type="submit">Generate Care Plan</button>
    </form>
    
    <hr style="margin: 40px 0;">
    <a href="/export/"><button type="button">Export All Records to CSV</button></a>
</body>
</html>
"""

# ============================================
# 12. app/templates/result.html
# ============================================
"""
<!DOCTYPE html>
<html>
<head>
    <title>Care Plan Result</title>
    <style>
        body { font-family: Arial; max-width: 900px; margin: 50px auto; padding: 20px; }
        .plan { background: #f5f5f5; padding: 20px; white-space: pre-wrap; }
        button { padding: 10px 20px; margin: 10px 5px 0 0; background: #28a745; color: white; border: none; cursor: pointer; }
        button:hover { background: #218838; }
        .back { background: #6c757d; }
        .back:hover { background: #5a6268; }
    </style>
</head>
<body>
    <h1>Generated Care Plan</h1>
    <p><strong>Patient:</strong> {{ care_plan.patient_first_name }} {{ care_plan.patient_last_name }}</p>
    <p><strong>MRN:</strong> {{ care_plan.patient_mrn }}</p>
    <p><strong>Medication:</strong> {{ care_plan.medication_name }}</p>
    
    <div class="plan">{{ care_plan.generated_plan }}</div>
    
    <a href="/download/{{ care_plan.id }}/"><button>Download as .txt</button></a>
    <a href="/"><button class="back">Create Another</button></a>
</body>
</html>
"""

# ============================================
# 13. manage.py
# ============================================
"""
#!/usr/bin/env python
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'careplan.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Couldn't import Django.") from exc
    execute_from_command_line(sys.argv)
"""

# ============================================
# 项目结构
# ============================================
"""
careplan_project/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env
├── manage.py
├── careplan/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── app/
    ├── __init__.py
    ├── models.py
    ├── views.py
    ├── urls.py
    ├── migrations/
    │   └── __init__.py
    └── templates/
        ├── form.html
        └── result.html
"""

# ============================================
# 启动命令
# ============================================
"""
1. 创建 .env 文件，填入你的 ANTHROPIC_API_KEY
2. docker-compose build
3. docker-compose up
4. 访问 http://localhost:8000
"""