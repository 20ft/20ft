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
import socket
import subprocess
import requests
import json
import psutil
import os
from base64 import b64encode, b64decode
from libnacl.public import SecretKey
from _thread import allocate_lock

docker_url_base = 'http+unix://%2Fvar%2Frun%2Fdocker.sock'
docker_bin = None
netstat_bin = None

try:
    docker_bin = subprocess.check_output(['which', 'docker']).decode().rstrip('\r\n')
except subprocess.CalledProcessError:
    pass

try:
    netstat_bin = subprocess.check_output(['which', 'netstat']).decode().rstrip('\r\n')
except subprocess.CalledProcessError:
    pass


class Waitable:
    """Wait for an object to be ready with wait_until_ready"""
    def __init__(self):
        self.wait_lock = allocate_lock()
        self.wait_lock.acquire()

    def __del__(self):
        if self.wait_lock.locked():
            self.wait_lock.release()

    def wait_until_ready(self):
        # this lock is used for waiting on while uploading layers, needs to be long
        result = self.wait_lock.acquire(timeout=120)
        self.wait_lock.release()
        return result

    def mark_as_ready(self):
        if self.wait_lock.locked():
            self.wait_lock.release()

    def mark_not_ready(self):
        if not self.wait_lock.locked():
            self.wait_lock.acquire()


class Killable:
    """The concept of an object having been destroyed, killed, terminated or whatever"""
    def __init__(self):
        self.dead = False

    def mark_as_dead(self):
        self.dead = True

    def bail_if_dead(self):
        # use this where the user is not really to blame
        if self.dead:
            logging.debug("Object was previously terminated (carrying on): " + self.__repr__())
        return self.dead

    def ensure_alive(self):
        # use this where the user has tried to use the object but it's kinda their fault it's no longer there
        if self.dead:
            raise ValueError("Cannot call method on a terminated object: " + self.__repr__())


class KeyPair:
    """Holds a public/secret key pair as base 64 - bytes not strings"""

    def __init__(self, name=None, prefix='~/.20ft'):
        self.public = None
        self.secret = None
        if name is None:
            return

        # we are also fetching the keys
        expand = os.path.expanduser(prefix)
        try:
            with open(expand + '/' + name + ".pub", 'rb') as f:
                self.public = f.read()[:-1]
        except FileNotFoundError:
            raise RuntimeError("No public key found, halting")
        try:
            with open(expand + '/' + name, 'rb') as f:
                self.secret = f.read()[:-1]
        except FileNotFoundError:
            raise RuntimeError("No private key found, halting")

    def public_binary(self):
        return b64decode(self.public)

    def secret_binary(self):
        return b64decode(self.secret)

    @staticmethod
    def new():
        """Create a new random key pair"""
        keys = SecretKey()
        rtn = KeyPair()
        rtn.public = b64encode(keys.pk)
        rtn.secret = b64encode(keys.sk)
        return rtn

    def __repr__(self):
        return "<tfnz.keys.Keys object at %x (pk=%s)>" % (id(self), self.public)


def description(docker_image_id) -> dict:
    """Describe a docker image.

    :return: A json representation of image metadata."""
    try:
        r = requests.get('%s/images/%s/json' % (docker_url_base, docker_image_id))
    except:
        raise RuntimeError("""Cannot connect to the docker socket.
-----------------------------------------------------
You need to run 'sudo chmod 666 /var/run/docker.sock'
-----------------------------------------------------""")
    obj = json.loads(r.text)
    if 'message' in obj:
        if obj['message'][0:14] == "No such image:":
            raise ValueError("Image not in local docker: " + docker_image_id)
    return obj


def last_image() -> str:
    """Finding the most recent docker image on this machine.

    :return: id of the most recently built docker image

    The intent is that last_image can be used as part of a development cycle (pass as image to spawn). """
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


def get_external_ip() -> str:
    """Finding the external IP for this machine/vm.

    :return: The external IP for this machine.

    This may not be an internet routable IP."""
    for interface in list(psutil.net_if_addrs().values()):
        for addr in interface:
            # Allow inet4, not localhost and not a bridge
            if addr.family == socket.AddressFamily.AF_INET and \
               addr.address[:3] != '127' and addr.address[:6] != '172.17' is not None:
                logging.info("Public bind IP: " + addr.address)
                return addr.address


def find_unused_local_port() -> int:
    """Find an unused local port number.

    :return: An unused local port number between 1025 and 8192.

    Port numbers are kept above 1024 so there is no need to run as root."""
    # find the used ports
    out = io.BytesIO(subprocess.check_output([netstat_bin, '-n', '-p', 'tcp'], stderr=subprocess.DEVNULL))
    out.readline()
    out.readline()
    ports = set()
    for line in out:
        try:
            props = line.split()
            ip_bits = props[3].decode().split('.')
            if len(ip_bits) != 5:
                continue  # an ip6 address
            ports.add(ip_bits[4])
        except:
            raise RuntimeError("Failed trying to find an open local port")

    # keep guessing until we get an empty one
    while True:
        candidate = random.randrange(1025, 8192)
        if candidate not in ports:
            return candidate


sys.excepthook = uncaught_exception
