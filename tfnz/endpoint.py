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

import weakref
import logging
import requests
import time
from requests.exceptions import ConnectionError, ReadTimeout
from typing import List, Optional, Tuple
from tfnz.container import Container


class Cluster:
    """An object representing a collection of containers, load balanced and published to an endpoint"""

    def __init__(self, containers: List[Container], rewrite: Optional[str]=None):
        self.uuid = None
        self.containers = {}
        self.rewrite = rewrite
        for container in containers:
            container.wait_until_ready()
            self._add(container)

    def uuids(self):
        return self.containers.keys()

    def _add(self, container):
        if container.uuid in self.containers:
            pass
        self.containers[container.uuid] = container

    def __repr__(self):
        return "<Cluster '%s' containers=%d>" % (self.uuid, len(self.containers))


class WebEndpoint:
    """An HTTP proxy that can expose a number of clusters"""

    def __init__(self, conn: 'Connection', domain: str):
        """Do not construct directly, see location.endpoints"""
        self.conn = weakref.ref(conn)
        self.domain = domain
        self.domainchars = len(domain)
        self.clusters = {}  # uuid to cluster

    def publish(self, cluster: Cluster, fqdn: str, *, ssl: Optional[Tuple]=None):
        # checks
        if not fqdn.endswith(self.domain):
            raise ValueError("Web endpoint for (%s) cannot publish: %s" % (self.domain, fqdn))
        subdomain = fqdn[:-self.domainchars]

        # ssl check and read
        combined = None
        if ssl is not None:
            if len(ssl) not in (2, 3):
                raise ValueError("SSL needs to be a tuple of (cert.pem, key.pem) or "
                                 "(cert.pem, key.pem, cert.intermediate")
            combined = ''
            with open(ssl[0]) as f:
                combined += f.read()
            with open(ssl[1]) as f:
                combined += f.read()
            if len(ssl) is 3:
                with open(ssl[2]) as f:
                    combined += f.read()

        # tell the location to publish
        msg = self.conn().send_blocking_cmd(b'publish_web', {'domain': self.domain,
                                                             'subdomain': subdomain,
                                                             'rewrite': cluster.rewrite,
                                                             'ssl': combined,
                                                             'containers': list(cluster.uuids())})
        logging.info("Published (%s) at: %s" % (msg.uuid.decode(), subdomain + self.domain))
        cluster.uuid = msg.uuid
        self.clusters[msg.uuid] = cluster
        return msg.uuid

    @staticmethod
    def wait_http_200(fqdn: str, *, ssl: Optional[bool]=False):
        """Poll the gateway for an http 200 from this cluster"""
        url = '%s://%s' % ('https' if ssl else 'http', fqdn)
        attempts_remaining = 30
        while True:
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    break
            except (ConnectionError, ConnectionRefusedError, ReadTimeout):
                pass
            attempts_remaining -= 1
            if attempts_remaining == 0:
                raise ValueError("Could not connect to: " + url)
            time.sleep(1)

    def unpublish(self, cluster: Cluster):
        self.conn().send_cmd(b'unpublish_web', {'uuid': cluster.uuid})
        logging.info("Unpublished: " + cluster.uuid.decode())
        del self.clusters[cluster.uuid]

    def __repr__(self):
        return "<WebEndpoint '%s' domain=%s>" % (self.uuid.decode(), self.domain)
