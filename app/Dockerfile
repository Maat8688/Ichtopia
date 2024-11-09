## Docker file for flask app
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY src /app/src
COPY static /app/static
COPY templates /app/templates
COPY requirements.txt /app
COPY .env /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make ports available to the world outside this container
EXPOSE 5000
EXPOSE 80

# Define environment variable
ENV NAME World

# Run app/src/app.py when the container launches
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=80"]
