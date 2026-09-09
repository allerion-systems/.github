FROM python:3.12-slim
WORKDIR /app
# Stdlib-only server. Products under products/ are zipped on the fly at delivery,
# so the whole app directory is copied in (.dockerignore trims the cruft).
COPY . .
ENV STORE_DB=/data/store.db
EXPOSE 8088
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8088"]
