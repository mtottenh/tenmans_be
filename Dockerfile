FROM python:3.12-alpine AS base

FROM base AS builder
RUN mkdir /installnpm
WORKDIR /install
COPY requirements.txt /requirements.txt
RUN pip install --prefix=/install -r /requirements.txt

FROM base

COPY --from=builder /install /usr/local
COPY src /app/src
WORKDIR /app
CMD ["fastapi", "run", "/app/src"]