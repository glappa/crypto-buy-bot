FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && mkdir /data
COPY *.py .
ENV DB_PATH=/data/buybot.db
VOLUME /data
CMD ["python", "bot.py"]
