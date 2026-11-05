FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
ARG INSTALL_NEURAL=false
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.lock.txt requirements-neural.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
RUN if [ "$INSTALL_NEURAL" = "true" ]; then pip install --no-cache-dir -r requirements-neural.txt --index-url https://download.pytorch.org/whl/cpu; fi
COPY backend ./backend
COPY data ./data
COPY scripts ./scripts
RUN useradd --create-home forecastiq && mkdir /app/storage && chown forecastiq:forecastiq /app/storage
USER forecastiq
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
