FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /agent
COPY agent.py .
CMD ["python", "agent.py", "--server", "http://server:8000", "--interval", "10"]
