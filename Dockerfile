FROM python:2.7-slim

# Increment this value to force apt-get update to run again.
ENV FORCE_UDPATE 5

RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y \
    build-essential \
    git \
    openjdk-7-jdk \
    ruby \
    ruby-dev \
    bundler \
    zlib1g-dev \
    libxml2 \
    libxml2-dev \
    libpq-dev

COPY . /app/
WORKDIR /app/

RUN cd connect_vbms && make
RUN cd connect_vbms && bundle install --path=vendor/bundle

RUN pip install -r requirements.txt
