FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt -q

RUN playwright install chromium

COPY . .

RUN mkdir -p photos sessions

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
