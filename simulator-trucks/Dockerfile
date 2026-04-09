FROM python:3.12-slim

WORKDIR /app

COPY simulator-trucks/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY simulator-trucks/ /app/simulator_trucks/

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "simulator_trucks.main"]
