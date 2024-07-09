from django.db import models
from django.utils import timezone

class UploadedFile(models.Model):
    user_id = models.CharField(max_length=100)
    file_path = models.CharField(max_length=255)
    file_id = models.CharField(max_length=100)
    file_type = models.CharField(max_length=50)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file_path

class ProcessedResult(models.Model):
    uploaded_file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE)
    result_path = models.CharField(max_length=255)
    processed_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.result_path








