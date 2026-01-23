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
    
    status = models.CharField(max_length=20, default='pending')  # pending/processing/completed/failed
    generated_plan = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)