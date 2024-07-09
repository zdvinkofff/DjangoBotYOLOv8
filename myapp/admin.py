from django.contrib import admin
from .models import UploadedFile, ProcessedResult

admin.site.register(UploadedFile)
admin.site.register(ProcessedResult)

