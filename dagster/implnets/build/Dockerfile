FROM python:3.12-slim

# Read the ARG implnet to set who to build for.

ARG implnet

# Change working directory
WORKDIR /usr/src/app
ENV DAGSTER_HOME=/usr/src/app

# git is needed to fetch the earthcube-utilities git dependency
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
# deps come from pyproject.toml, pinned by uv.lock
# --no-hashes: earthcube-utilities is a git dependency and cannot be hashed,
# and pip refuses a requirements file that mixes hashed and unhashed entries.
COPY ./pyproject.toml ./uv.lock ./
RUN pip install uv \
    && uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

# Copy source code
COPY ./dagster.yaml .
COPY ./generatedCode/implnet-${implnet}/output .

CMD ["dagit", "-w", "workspace.yaml", "-h", "0.0.0.0", "-p", "3000"]
