# ColdGuard Simulator Guide

The ColdGuard Simulator is a Python-based CLI tool designed to generate realistic temperature telemetry data and automatically stream it to the backend Ingestion API. It supports multiple scenarios out-of-the-box, such as excursions and sensor failures, to help you test the ColdGuard alert engines.

## 1. Setup

The simulator relies on its own `.env` file to locate the API and authenticate.
```bash
cd simulator
cp .env.example .env
pip install -r requirements.txt
```
> [!NOTE]
> The default credentials (`simulator@coldguard.com` / `simulator123`) correspond to the `OPERATOR` account created by the backend seed script.

## 2. Running Scenarios

The CLI allows you to simulate various behaviors. If you don't specify a `storage-unit` or `sensor` ID, it will query the API and automatically attach to the first available sensor.

### Normal Operation
Simulates stable temperature around a set baseline with minor Gaussian noise.
```bash
python simulator.py --scenario normal --start-temp 4.5
```

### High Temperature Excursion
Simulates a sudden spike in temperature, triggering high-temperature alarms in the backend.
```bash
python simulator.py --scenario high-excursion --start-temp 4.5
```
*Expected Behavior*: The temperature will spike by ~5.0°C during the middle third of the simulation, causing values like `9.8°C`.

### Low Temperature Excursion
Simulates a sudden drop in temperature, typically causing freezing alerts for sensitive products like vaccines.
```bash
python simulator.py --scenario low-excursion --start-temp 4.5
```
*Expected Behavior*: The temperature will drop by ~4.0°C, causing values like `0.5°C`.

### Gradual Failure Scenarios
Useful for testing predictive maintenance alerts.
```bash
# Simulates a compressor slowly failing (warming up)
python simulator.py --scenario gradual-increase --start-temp 4.5

# Simulates a stuck cooling valve (freezing over)
python simulator.py --scenario gradual-decrease --start-temp 4.5
```

### Data Loss / Hardware Failure
```bash
# Simulates missed API calls (network drops)
python simulator.py --scenario missing-readings

# Simulates explicit hardware error flags (quality_status = 'error', temp = -999.9)
python simulator.py --scenario sensor-failure
```

## 3. Configuration Flags

You can customize the simulation using the following flags:
- `--interval`: Seconds between API calls (default: `5`).
- `--duration`: Total time in seconds to run before auto-stopping (default: `60`). Set to `0` for infinite execution.
- `--start-temp`: The baseline temperature in Celsius (default: `4.5`).
- `--storage-unit`: Manually override the UUID of the storage unit.
- `--sensor`: Manually override the UUID of the sensor.
