FROM python:3.12-alpine

RUN apk add --no-cache ffmpeg 

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/files

EXPOSE 5000

CMD ["sh", "-c", "gunicorn -b 0.0.0.0:5000 main:app -k eventlet -w ${GUNICORN_WORKERS}"]