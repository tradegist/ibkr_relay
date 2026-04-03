FROM python:3.11-slim

WORKDIR /app

COPY poller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY poller/models.py .
COPY poller/main.py .
COPY poller/poller/__init__.py poller/poller/flex_parser.py ./poller/
COPY poller/routes/__init__.py poller/routes/middlewares.py poller/routes/run.py ./routes/

CMD ["python", "-u", "main.py"]
