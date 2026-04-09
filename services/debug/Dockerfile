FROM python:3.11-slim

WORKDIR /app

COPY services/debug/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/debug/debug_app.py .

CMD ["python", "-u", "debug_app.py"]
