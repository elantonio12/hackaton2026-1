FROM python:3.12-slim

WORKDIR /app

# Install the simulator package into /app/simulator/ so that
# `python -m simulator.main` resolves correctly.
COPY requirements.txt /app/simulator/requirements.txt
RUN pip install --no-cache-dir -r /app/simulator/requirements.txt

COPY . /app/simulator/

CMD ["python", "-m", "simulator.main"]
