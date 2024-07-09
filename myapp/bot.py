import telebot
import cv2
import numpy as np
import os
import logging.config
import traceback
import threading
from moviepy.video.io.VideoFileClip import VideoFileClip
from telebot import types
from ultralytics import YOLO
from PIL import Image
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()
from myapp.models import UploadedFile, ProcessedResult
from django.utils import timezone


LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging_config = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'bot.log'),
            'formatter': 'default',
            'encoding': 'utf-8'
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        }
    },
    'loggers': {
        '': {
            'handlers': ['file', 'console'],
            'level': logging.DEBUG,
            'propagate': True
        }
    }
}

logging.config.dictConfig(logging_config)
logger = logging.getLogger(__name__)

logger.info("Logger initialized successfully.")

# Инициализация бота
TOKEN = '6797762359:AAG27mStq9FE0RRKnJePZKcaTNNsvdROH3I'
bot = telebot.TeleBot(TOKEN)

# Загрузка модели YOLOv8
model = YOLO('yolov8n.pt')

# Убедитесь, что существуют директории
DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Максимальный размер файла (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024
# Максимальная длительность видео (10 секунд)
MAX_VIDEO_DURATION = 10

stop_flag = threading.Event()
stop_video_flag = threading.Event()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    photo_button = types.KeyboardButton("Загрузить фото")
    video_button = types.KeyboardButton("Загрузить видео (макс. 10MB или 10 сек.)")
    stop_button = types.KeyboardButton("Стоп")
    markup.add(photo_button, video_button, stop_button)
    bot.send_message(message.chat.id, 'Привет, пользователь:)! Я могу обрабатывать ваши фото и видео с помощью нейросети YOLOv8. Просто отправьте мне файл:', reply_markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = "Я могу обрабатывать ваши фото и видео с помощью нейросети YOLOv8. Просто отправьте мне файл."
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['stop'])
def stop_bot_handler(message):
    bot.send_message(message.chat.id, "Бот останавливается...")
    stop_flag.set()
    stop_video_flag.set()

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == "Загрузить фото":
        bot.send_message(message.chat.id, "Пожалуйста, отправьте мне фото.")
    elif message.text == "Загрузить видео (макс. 10MB или 10 сек.)":
        bot.send_message(message.chat.id, "Пожалуйста, отправьте мне видео (максимальный размер 10MB или длительность 10 секунд).")
    elif message.text == "Стоп":
        stop_video_flag.set()
        bot.send_message(message.chat.id, "Процесс остановлен.")

@bot.message_handler(content_types=['photo', 'video'])
def process_media(message):
    global processing_file
    try:
        file_id = None
        file_type = None

        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        elif message.video:
            file_id = message.video.file_id
            file_type = 'video'

        if file_id and file_type:
            file_info = bot.get_file(file_id)

            if file_info.file_size > MAX_FILE_SIZE:
                bot.send_message(message.chat.id, 'Файл слишком большой. Максимальный размер файла - 10MB.')
                return

            downloaded_file = bot.download_file(file_info.file_path)

            if file_type == 'photo':
                file_path = os.path.join(DOWNLOADS_DIR, f"{file_id}.jpg")
                with open(file_path, 'wb') as new_file:
                    new_file.write(downloaded_file)
                results = model(file_path)
            elif file_type == 'video':
                file_path = os.path.join(DOWNLOADS_DIR, f"{file_id}.mp4")
                with open(file_path, 'wb') as new_file:
                    new_file.write(downloaded_file)
                video_clip = VideoFileClip(file_path)
                if video_clip.duration > MAX_VIDEO_DURATION:
                    bot.send_message(message.chat.id, 'Видео слишком длинное. Максимальная длительность видео - 10 секунд.')
                    return

                results = model.track(source=file_path, stream=True)

            uploaded_file = UploadedFile(
                user_id=message.chat.id,
                file_id=file_id,
                file_type=file_type,
                file_path=file_path,
                uploaded_at=timezone.now()
            )
            uploaded_file.save()

            if file_type == 'photo':
                annotated_image = Image.fromarray(results[0].plot())
                result_path = os.path.join(RESULTS_DIR, f"{file_id}_result.jpg")
                annotated_image.save(result_path, 'JPEG', quality=100)
                if os.path.exists(result_path):
                    with open(result_path, 'rb') as f:
                        bot.send_photo(message.chat.id, f, disable_notification=True)
                else:
                    bot.send_message(message.chat.id, 'Извините, не удалось обработать изображение.')
            elif file_type == 'video':
                stop_video_flag.clear()
                for idx, result in enumerate(results):
                    if stop_video_flag.is_set():
                        bot.send_message(message.chat.id, 'Процесс остановлен пользователем.')
                        break
                    annotated_frame = Image.fromarray(result.plot())
                    result_path = os.path.join(RESULTS_DIR, f"{file_id}_result_{idx}.jpg")
                    annotated_frame.save(result_path, 'JPEG', quality=100)
                    if os.path.exists(result_path):
                        with open(result_path, 'rb') as f:
                            bot.send_photo(message.chat.id, f, disable_notification=True)
                    else:
                        bot.send_message(message.chat.id, 'Извините, не удалось обработать видео.')

            processed_result = ProcessedResult(
                uploaded_file=uploaded_file,
                result_path=result_path,
                processed_at=timezone.now()
            )
            processed_result.save()

        else:
            bot.send_message(message.chat.id, 'Извините, я не смог распознать отправленный файл.')
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
        logger.error(traceback.format_exc())
        bot.send_message(message.chat.id, 'Произошла ошибка при обработке вашего запроса. Попробуйте снова.')

def save_result(message, file_path, result_path):
    """
    Сохранение результата обработки в базу данных.
    """
    try:
        user_id = message.chat.id
        file_id = message.document.file_id
        file_type = message.document.mime_type

        uploaded_file = UploadedFile(
            user_id=user_id,
            file_path=file_path,
            file_id=file_id,
            file_type=file_type,
            uploaded_at=timezone.now()
        )
        uploaded_file.save()

        logger.info(f"Saving result: {result_path}")
        processed_result = ProcessedResult(
            uploaded_file=uploaded_file,
            result_path=result_path
        )
        processed_result.save()
        logger.info(f"Result saved: {result_path}")
    except Exception as e:
        logger.error(f"Произошла ошибка при сохранении результата: {e}")
        bot.send_message(message.chat.id, 'Произошла ошибка при сохранении результата обработки.')

def process_photo(file_path, message):
    """
    Обработка фотографий с помощью модели YOLOv8.
    """
    try:
        results = model(file_path)
        image = Image.open(file_path)
        image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0]
                cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (36, 255, 12), 2)

        image_bytes = cv2.imencode('.jpg', image)[1].tobytes()
        bot.send_photo(chat_id=message.chat.id, photo=image_bytes, caption='Обработанное фото:')

        # Сохранение результата в базе данных
        save_result(message, file_path, image_bytes)
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
        logger.error("Traceback:", exc_info=True)
        bot.send_message(message.chat.id, f"Произошла ошибка при обработке фото: {e}")


def process_video(file_path, message):
    try:
        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        num_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = num_frames / fps
        if duration > MAX_VIDEO_DURATION:
            bot.send_message(message.chat.id, f'Длительность видео превышает максимальную ({MAX_VIDEO_DURATION} секунд).')
            return

        result_file_path = os.path.join(RESULTS_DIR, os.path.basename(file_path))

        clip = VideoFileClip(file_path)
        processed_clip = clip.fx(process_frame, model)
        processed_clip.write_videofile(result_file_path)

        with open(result_file_path, 'rb') as file:
            bot.send_video(chat_id=message.chat.id, video=file, caption='Обработанное видео:')

        uploaded_file = UploadedFile.objects.get(file_path=file_path)
        save_result(message, file_path, result_file_path, uploaded_file)
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
        logger.error("Traceback:", exc_info=True)
        bot.send_message(message.chat.id, f"Произошла ошибка при обработке видео: {e}")

def process_frame(frame, model):
    results = model(frame)
    boxes = results[0].boxes
    for box in boxes:
        x1, y1, x2, y2 = box.xyxy[0]
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (36, 255, 12), 2)
    return frame


@bot.message_handler(commands=['stop'])
def stop_processing(message):
    global stop_flag
    stop_flag.set()
    bot.send_message(chat_id=message.chat.id, text="Обработка остановлена.")

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
    Доступные команды:
    /start - начать работу с ботом
    /stop - остановить обработку
    /help - показать справку
    """
    bot.send_message(chat_id=message.chat.id, text=help_text)

def main():
    bot.polling(non_stop=True)

if __name__ == '__main__':
    main()
