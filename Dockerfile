FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .
COPY models.yaml ./
RUN useradd --create-home --uid 10001 bot
# Create and own the SQLite directory BEFORE dropping privileges. Without this the
# image has no /app/data, so Docker creates the mounted volume root-owned and the
# unprivileged bot user cannot open the database -- the container crash-loops on
# "unable to open database file" at first start.
RUN mkdir -p /app/data && chown -R bot:bot /app/data
USER bot
CMD ["python", "-m", "bot"]
