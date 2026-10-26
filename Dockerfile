FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir discord.py python-dotenv

COPY . .

CMD ["python", "bot.py"]   