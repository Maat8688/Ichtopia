## Docker file for flask app
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Install dependencies first so that editing application code does not
# invalidate the (slow) pip layer on every rebuild.
COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY src /app/src
COPY static /app/static
COPY templates /app/templates

# NOTE: .env is deliberately NOT copied into the image - secrets would be
# baked into every layer. It is supplied at run time via `env_file` in
# docker-compose.yaml (and by the `.:/app` bind mount for `flask run`).

# Make ports available to the world outside this container
EXPOSE 5000
EXPOSE 80

# Define environment variable
ENV NAME World

# Run app/src/app.py when the container launches
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=80"]
