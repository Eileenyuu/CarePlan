from django.db import models


class Patient(models.Model):
    """病人表：独立管理患者信息，MRN 全局唯一"""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    mrn = models.CharField(max_length=6, unique=True)
    date_of_birth = models.DateField()

    def __str__(self):
        return f"{self.first_name} {self.last_name} (MRN: {self.mrn})"


class Provider(models.Model):
    """医生表：独立管理 Provider 信息，NPI 全局唯一"""
    name = models.CharField(max_length=200)
    npi = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return f"{self.name} (NPI: {self.npi})"


class Order(models.Model):
    """订单表：关联病人和医生，包含处方/诊断信息"""
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='orders')
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='orders')
    medication_name = models.CharField(max_length=200)
    primary_diagnosis = models.CharField(max_length=20)
    additional_diagnosis = models.TextField(blank=True)
    medication_history = models.TextField(blank=True)
    clinical_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id}: {self.medication_name} for {self.patient}"


class CarePlan(models.Model):
    """Care Plan 表：一个订单对应一个 Care Plan，包含 LLM 生成的内容和状态"""
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='care_plan')
    status = models.CharField(max_length=20, default='pending')  # pending/processing/completed/failed
    generated_plan = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"CarePlan #{self.id} ({self.status}) for Order #{self.order_id}"