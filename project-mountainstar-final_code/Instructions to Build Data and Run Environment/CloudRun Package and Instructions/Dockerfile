FROM python:3.11-slim

# Install minimal OS dependencies (add more later if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application (app.py, notebooks, streamlit config, etc.)
COPY . .

# Streamlit theme + config (adjust path if your config lives elsewhere)
ENV STREAMLIT_THEME_BASE=dark
ENV STREAMLIT_CONFIG=/app/streamlit/config.toml

# Cloud Run will set $PORT; default to 8080 if not set
ENV PORT=8080

# Expose the port (for documentation; Cloud Run uses $PORT)
EXPOSE 8080

# Entrypoint: run Streamlit on 0.0.0.0:$PORT
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8080} --server.headless true --server.address=0.0.0.0"]
