FROM python:3.12-slim
WORKDIR /app
# Stdlib-only app — no pip install needed.
COPY server.py billing.py ./
ENV ALLERION_CRM_DB=/data/crm.db
EXPOSE 8099
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8099"]
