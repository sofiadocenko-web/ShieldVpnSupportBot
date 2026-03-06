FROM python:3.12-slim

WORKDIR /app

# Установите зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скопируйте код
COPY . .

# Запустите бота
CMD ["python", "main.py"]
