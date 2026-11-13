# Build context: repository root (shares backend/app/simulation/scenarios.py — no duplicated logic)
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --system --uid 10002 sim
WORKDIR /app
COPY simulator/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/app/simulation/scenarios.py ./scenarios.py
COPY simulator/simulator.py ./simulator.py
USER 10002
ENTRYPOINT ["python", "simulator.py"]
