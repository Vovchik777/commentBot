import sys
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(__file__))

# Импортируем наше приложение
from app import application
print("123")