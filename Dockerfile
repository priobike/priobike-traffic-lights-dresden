FROM python:3.12 as converter
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . .
# Healthcheck: health.txt may contain "ok" or "error"
HEALTHCHECK --start-period=60s \
    CMD test -f health.txt && grep -q "ok" health.txt || exit 1
CMD ["python", "src/converter.py"]

FROM python:3.12 as generator
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . .
# Healthcheck: health.txt may contain "ok" or "error"
HEALTHCHECK --start-period=10s \
    CMD test -f health.txt && grep -q "ok" health.txt || exit 1
CMD ["python", "src/generator.py"]