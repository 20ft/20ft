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

    def __init__(self, *, containers: Optional[List[Container]]=None, rewrite: Optional[str]=None):
        """Create a cluster.

        :param containers: An optional list of containers to initialise the cluster with.
        :param rewrite: An optional string to be rewritten into the http host header."""
        self.uuid = None
        self.conn = None
        self.containers = {}
        self.rewrite = rewrite
        for container in containers:
            self.add_container(container)

    def add_container(self, container):
        """Add a container to the cluster.

        :param container: the container to add."""
        if container.uuid in self.containers:
            pass
        container.wait_until_ready()
        self.containers[container.uuid] = container

        # let the server know, maybe
        if self.conn is not None:
            self.conn().send_blocking_cmd(b'add_to_cluster', {'cluster': self.uuid,
                                                              'container': container.uuid})

    def remove_container(self, container):
        """Remove a container from the cluster.

        :param container: the container to remove."""
        try:
            del self.containers[container.uuid]

            # let the server know, maybe
            if self.conn is not None:
                self.conn().send_cmd(b'remove_from_cluster', {'cluster': self.uuid,
                                                              'container': container.uuid})
        except KeyError:  # was not in the list of containers
            pass

    def uuids(self):
        return self.containers.keys()

    def __repr__(self):
        return "<Cluster '%s' containers=%d>" % (self.uuid, len(self.containers))


class WebEndpoint:
    """An HTTP proxy that can expose a number of clusters"""

    def __init__(self, conn: 'Connection', domain: str):
        """Do not construct directly, see location.endpoints"""
        self.conn = weakref.ref(conn)
        self.domain = domain
        self.clusters = {}  # uuid to cluster

    def publish(self, cluster: Cluster, fqdn: str, *, ssl: Optional[Tuple]=None):
        """Publish a cluster onto an http/https endpoint.
        To update a cluster, merely re-publish onto the same endpoint.

        :param cluster: The cluster to publish.
        :param fqdn: The fqdn to publish.
        :param ssl: A tuple of (cert.pem, key.pem) or (cert.pem, key.pem, cert.intermediate)."""
        # checks
        if not fqdn.endswith(self.domain):
            raise ValueError("Web endpoint for (%s) cannot publish: %s" % (self.domain, fqdn))
        if cluster.uuid in self.clusters:  # already published
            return

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
        subdomain = fqdn[:-len(self.domain)]
        msg = self.conn().send_blocking_cmd(b'publish_web', {'domain': self.domain,
                                                             'subdomain': subdomain,
                                                             'rewrite': cluster.rewrite,
                                                             'ssl': combined,
                                                             'containers': list(cluster.uuids())})
        logging.info("Published (%s) at: %s" % (msg.uuid.decode(), subdomain + self.domain))

        cluster.uuid = msg.uuid
        cluster.conn = weakref.ref(self.conn())
        self.clusters[msg.uuid] = cluster
        return msg.uuid

    @staticmethod
    def wait_http_200(fqdn: str, *, ssl: Optional[bool]=False):
        """Poll the gateway for an http 200 from this cluster.

        :param fqdn: the fqdn to poll.
        :param ssl: optionally connect via ssl."""
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
        """Remove a cluster from a web endpoint.

        :param cluster: the cluster to remove."""
        if cluster.uuid is None or cluster.uuid not in self.clusters:  # not published anyway
            return

        self.conn().send_cmd(b'unpublish_web', {'cluster': cluster.uuid})
        logging.info("Unpublished: " + cluster.uuid.decode())
        cluster.conn = None
        del self.clusters[cluster.uuid]

    def __repr__(self):
        return "<WebEndpoint '%s' clusters=%d>" % (self.domain, len(self.clusters))
