# Test image: Home Assistant does not run natively on Windows, so the
# integration tests run in this Linux container.
#   docker build -f docker/test.Dockerfile -t heat-conductor-test .
#   docker run --rm -v "${PWD}:/work" heat-conductor-test
FROM python:3.14-slim

WORKDIR /work
COPY requirements_test.txt /tmp/requirements_test.txt
RUN pip install --no-cache-dir -r /tmp/requirements_test.txt

CMD ["python", "-m", "pytest", "tests", "-q"]
