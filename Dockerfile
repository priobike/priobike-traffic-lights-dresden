FROM python:3.12 as converter

# Needed to fetch all things from the server
ENV FROST_BASE_URL="https://priobike.vkw.tu-dresden.de/staging/frost-server-web/FROST-Server/v1.1/"
# Broker that publishes the control messages
ENV CTRLMESSAGES_MQTT_HOST=""
ENV CTRLMESSAGES_MQTT_PORT=""
ENV CTRLMESSAGES_MQTT_USER=""
ENV CTRLMESSAGES_MQTT_PASS=""
# Needed to publish observations to the mqtt broker
ENV FROST_MQTT_HOST="priobike.vkw.tu-dresden.de"
ENV FROST_MQTT_PORT="20056"
ENV FROST_MQTT_USER=""
ENV FROST_MQTT_PASS=""

COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . .
# Healthcheck: health.txt may contain "ok" or "error"
HEALTHCHECK --start-period=60s \
    CMD test -f health.txt && grep -q "ok" health.txt || exit 1
CMD ["python", "src/converter.py"]

FROM python:3.12 as generator

# Needed to fetch all things from the server
ENV FROST_BASE_URL="https://priobike.vkw.tu-dresden.de/staging/frost-server-web/FROST-Server/v1.1/"
# Needed to publish observations to the mqtt broker
ENV FROST_MQTT_HOST="priobike.vkw.tu-dresden.de"
ENV FROST_MQTT_PORT="20056"
ENV FROST_MQTT_USER=""
ENV FROST_MQTT_PASS=""

COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . .
# Healthcheck: health.txt may contain "ok" or "error"
HEALTHCHECK --start-period=10s \
    CMD test -f health.txt && grep -q "ok" health.txt || exit 1
CMD ["python", "src/generator.py"]