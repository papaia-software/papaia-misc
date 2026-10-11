FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY app app
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .
COPY alembic alembic
COPY alembic.ini .
RUN useradd --create-home papaia && chown -R papaia:papaia /app
USER papaia
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
