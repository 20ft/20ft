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

# It does, indeed, need *all* these headers, and 'make' etc. etc.
# docker build --squash -t tfnz/tfnz .

FROM alpine
RUN apk update
RUN apk upgrade
RUN apk add python3 gcc make python3-dev py3-certifi zlib zlib-dev libc-dev linux-headers py3-zmq libffi libffi-dev openssl openssl-dev

RUN pip3 install tfnz

RUN apk del gcc make python3-dev zlib-dev libc-dev linux-headers libffi-dev openssl-dev
RUN rm -rf /var/cache /etc/motd
RUN find / -name "*.o" | xargs rm $0
