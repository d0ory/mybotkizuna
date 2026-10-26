FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "discord.py>=2.3.2" python-dotenv   

COPY . .

CMD ["python", "bot.py"]   