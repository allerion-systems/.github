FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY billing_sync.py setup_stripe.py ./

# Long-running worker; logs to stdout (-u for unbuffered).
CMD ["python", "-u", "billing_sync.py"]
