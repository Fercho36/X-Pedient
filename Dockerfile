FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libffi-dev python3-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_ENV=production
ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
