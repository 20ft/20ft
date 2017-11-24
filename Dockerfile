FROM alpine
RUN apk update
RUN apk add python3 gcc make python3-dev py3-certifi libc-dev linux-headers py3-zmq libffi-dev openssl-dev git
RUN pip3 install --upgrade pip

RUN git clone https://github.com/msabramo/requests-unixsocket.git; \
    cd requests-unixsocket; \
    python3 setup.py install; \
    cd ..; \
    rm -rf requests-unixsocket

COPY dist/tfnz-1.1.7.tar.gz /
RUN pip3 install tfnz-1.1.7.tar.gz ; rm /tfnz-*

RUN apk del gcc linux-headers git ; rm -rf /var/cache /etc/motd
