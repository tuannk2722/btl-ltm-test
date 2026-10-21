FROM python:3.12-slim
WORKDIR /app
COPY src/ ./src/
ENV PYTHONUNBUFFERED=1
EXPOSE 5000
CMD ["python", "-u", "src/server.py"]
