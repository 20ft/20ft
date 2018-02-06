# Copyright (c) 2018 David Preece, All rights reserved.
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

# You may wish to create a synchronous volume for databases...
# tfvolumes create --sync postgres_data

from tfnz.location import Location
from tfnz.volume import Volume
import random
import string


class Postgresql:
    def __init__(self, location: Location, volume: Volume, *, password: str=None, log_callback=None):
        """Instantiate a postgresql server container. Connect with username=postgres.

        :param location: A location (object) to connect to.
        :param volume: A volume (object) to use as a persistent store.
        :param password: An optional password for the database, will create one if not supplied.
        :param log_callback: An optional callback for log messages -  signature (object, bytes)"""
        # passwords
        if password is None:
            self.password = ''.join(random.SystemRandom().choice(string.ascii_letters+string.digits) for _ in range(12))
        else:
            self.password = password

        # create
        self.node = location.node()
        self.ctr = self.node.spawn_container('postgres:alpine',
                                             env=[('POSTGRES_PASSWORD', self.password)],
                                             volumes=[(volume, '/var/lib/postgresql/data')],
                                             stdout_callback=log_callback).wait_until_ready()

    def wait_until_ready(self):
        """Wait until Postgres is actually able to respond to queries"""
        self.ctr.wait_tcp(5432)

    def attach_tunnel(self):
        """Attach a tcp tunnel to Postgres"""
        return self.ctr.attach_tunnel(5432)
