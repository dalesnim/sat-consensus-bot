FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .
COPY models.yaml ./
RUN useradd --create-home --uid 10001 bot
USER bot
CMD ["python", "-m", "bot"]
