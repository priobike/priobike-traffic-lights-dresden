FROM python:3.12 as converter
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "src/converter.py"]

FROM python:3.12 as generator
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "src/generator.py"]