FROM python:3.7

# Install requirements
COPY requirements.txt /app/requirements.txt
WORKDIR /app

RUN pip install -r requirements.txt

# Copy the rest of the code
COPY runner.py /app/runner.py

# Run the code
CMD ["python", "runner.py"]