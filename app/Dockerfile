## Docker file for flask app
FROM python:3.12-slim

WORKDIR /app

# Eerst alleen de requirements, zodat pip install gecached blijft bij codewijzigingen.
COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src
COPY static /app/static
COPY templates /app/templates
COPY data /app/data
COPY migrations /app/migrations
# Geen .env in de image: de geheimen komen bij het starten binnen via
# docker-compose (environment). Zo staan ze niet in elke kopie van de image.

# Niet als root draaien.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/log && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["gunicorn", "src:app", "--worker-class", "gthread", "--workers", "1", "--threads", "100", "--bind", "0.0.0.0:8000", "--timeout", "120"]
