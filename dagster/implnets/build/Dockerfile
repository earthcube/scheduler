FROM python:3.13-slim

# Read the ARG implnet to set who to build for.

ARG implnet

# Change working directory
WORKDIR /usr/src/app
ENV DAGSTER_HOME=/usr/src/app

# Install dependencies
# deps come from pyproject.toml, pinned by uv.lock
COPY ./pyproject.toml ./uv.lock ./
RUN pip install uv \
    && uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

# Copy source code
COPY ./dagster.yaml .
COPY ./generatedCode/implnet-${implnet}/output .

CMD ["dagit", "-w", "workspace.yaml", "-h", "0.0.0.0", "-p", "3000"]
