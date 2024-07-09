from django.shortcuts import render
from django.http import HttpResponse
from .models import UploadedFile, ProcessedResult

def index(request):
    # Обработка запросов, если необходимо
    return HttpResponse("Привет, это ваше Django приложение.")

# Другие функции представлений, если они есть

