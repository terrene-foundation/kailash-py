FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    postgresql-client \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt requirements-test.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-test.txt

# Copy application code
COPY . .

# Install kailash in development mode
RUN pip install -e .

# Create test results directory
RUN mkdir -p /app/test_results

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTEST_CURRENT_TEST=1

# Default command runs all tests
CMD ["pytest", "tests/", "-v", "--tb=short"]
