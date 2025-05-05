FROM debian:bookworm-slim as cards_cdb_fetcher

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN wget -O cards.cdb https://cdn02.moecube.com:444/ygopro-database/zh-CN/cards.cdb

FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
COPY --from=cards_cdb_fetcher /app/cards.cdb ./cards.cdb
RUN python card_build.py

ENTRYPOINT ["python"]
CMD ["guess_card_game.py"]
