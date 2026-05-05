
FROM python:3.12-slim
WORKDIR /app
# Install system dependencies for rasterio & GDAL 
# Install GDAL + Rasterio specially to protect the environment
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    gdal-bin libgdal-dev \
    libgeos-dev proj-bin libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*
# Copy dependencies and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy project source and dependency files to the container
COPY src /app/src
COPY dependencies /app/dependencies
ENV PYTHONPATH=/app:/app/src
CMD ["/bin/bash"]
