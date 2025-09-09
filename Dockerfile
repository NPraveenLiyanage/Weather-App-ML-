# Root Dockerfile for Vercel build context
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Install dependencies
COPY weatherProject/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the whole repository into the container
COPY . .

# Copy the project entrypoint and make it executable
COPY weatherProject/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Entrypoint will run migrations, collectstatic and then start the server
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["gunicorn", "weatherProject.wsgi:application", "--bind", "0.0.0.0:${PORT:-8000}"]
