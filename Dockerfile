# Copyright (c) 2017 David Preece, All rights reserved.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

FROM alpine
RUN apk update
RUN apk add python3 gcc make python3-dev py3-certifi libc-dev linux-headers py3-zmq libffi-dev openssl-dev git
RUN pip3 install --upgrade pip

RUN git clone https://github.com/msabramo/requests-unixsocket.git; \
    cd requests-unixsocket; \
    python3 setup.py install; \
    cd ..; \
    rm -rf requests-unixsocket

COPY dist/tfnz-1.1.11.tar.gz /
RUN pip3 install tfnz-1.1.11.tar.gz ; rm /tfnz-*

RUN apk del gcc linux-headers git ; rm -rf /var/cache /etc/motd
