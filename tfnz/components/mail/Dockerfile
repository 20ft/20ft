# docker build -t tfnz/mail .
FROM alpine
RUN apk update ; apk add exim
RUN mkdir -p /var/log/exim/ ; \
    touch /var/log/exim/mainlog ; \
    chown 100:101 /var/log/exim/* ; \
    mkdir -p /var/mail ; \
    chown 100:101 /var/mail ; \
    mkdir -p /usr/lib/exim/ ; \
    chown 100:101 /usr/lib/exim/
