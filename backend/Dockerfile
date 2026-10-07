FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY ml/ ./ml/
COPY database/schema.sql ./database/
WORKDIR /app/backend
RUN chmod +x entrypoint.sh
EXPOSE 8000
# Seeds the DB on first boot if absent, then serves (see entrypoint.sh).
CMD ["./entrypoint.sh"]
