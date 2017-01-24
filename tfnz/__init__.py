"""Copyright (c) 2017 David Preece, All rights reserved.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

import logging
import sys
import traceback
import io
import random
import subprocess
import requests
import json

docker_url_base = 'http+unix://%2Fvar%2Frun%2Fdocker.sock'


def description(docker_image_id) -> dict:
    # Get metadata from local Docker.
    r = requests.get('%s/images/%s/json' % (docker_url_base, docker_image_id))
    obj = json.loads(r.text)
    if 'message' in obj:
        if obj['message'][0:14] == "No such image:":
            raise ValueError("Image not in local docker: " + docker_image_id)
    return obj


def last_image() -> str:
    """Finding the most recent docker image on this machine.

       The intent is that last_image can be used as part of a development cycle (pass as image to spawn)."""
    r = requests.get('%s/images/json' % docker_url_base)
    if len(r.text) == 0:
        raise ValueError("Docker has no local images.")
    obj = json.loads(r.text)
    return obj[0]['Id'][7:19]


def uncaught_exception(exctype, value, tb):
    if exctype is KeyboardInterrupt:
        logging.info("Caught Ctrl-C, closing")  # clearing server side objects done by server
        exit(0)
    traceback.print_exception(exctype, value, tb)
    exit(1)


def find_unused_local_port() -> int:
    # find the used ports
    out = io.BytesIO(subprocess.check_output(['/usr/sbin/netstat', '-n', '-f', 'inet', '-p', 'tcp']))
    out.readline()
    out.readline()
    ports = set()
    for line in out:
        try:
            props = line.split()
            ip_bits = str(props[3], 'ascii').split('.')
            ports.add(ip_bits[4])
        except:
            raise RuntimeError("Failed trying to find an open local port")

    # keep guessing until we get an empty one
    while True:
        candidate = random.randrange(1025, 8192)
        if candidate not in ports:
            return candidate


sys.excepthook = uncaught_exception
