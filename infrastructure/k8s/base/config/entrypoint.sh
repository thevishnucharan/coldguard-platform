#!/bin/sh
# Builds the Mosquitto password file from environment variables at start-up so no
# credentials are baked into the image or committed to the repository.
set -e
: "${MQTT_INGESTOR_PASSWORD:?MQTT_INGESTOR_PASSWORD must be set}"
: "${MQTT_DEVICE_PASSWORD:?MQTT_DEVICE_PASSWORD must be set}"
cp /config-src/mosquitto.conf /mosquitto/config/mosquitto.conf
cp /config-src/acl /mosquitto/config/acl
rm -f /mosquitto/config/passwd
mosquitto_passwd -b -c /mosquitto/config/passwd coldguard-ingestor "$MQTT_INGESTOR_PASSWORD"
mosquitto_passwd -b /mosquitto/config/passwd coldguard-device "$MQTT_DEVICE_PASSWORD"
chown mosquitto:mosquitto /mosquitto/config/passwd /mosquitto/config/acl 2>/dev/null || true   # no-op when already running as the mosquitto user (k8s restricted PSS)
chmod 0700 /mosquitto/config/passwd /mosquitto/config/acl
exec mosquitto -c /mosquitto/config/mosquitto.conf
