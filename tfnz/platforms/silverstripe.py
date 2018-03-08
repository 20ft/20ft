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

import logging
from tfnz.location import Location
from tfnz.volume import Volume
from tfnz.components.postgresql import Postgresql
from tfnz.endpoint import WebEndpoint, Cluster


class SilverStripe:
    """Puts a PHP/SilverStripe instance on each node and load balances.

    :param location: A location (object) to connect to.
    :param volume: A volume (object) to use as a persistent store.
    :param sql_volume: A volume to connect to a Postgres server for SQL storage.
    :param fqdn: The FQDN to publish to.
    :param image: Use a non-default container image.
    :param log_callback: An optional callback for log messages -  signature (object, bytes)"""

    def __init__(self, location: Location, volume: Volume, sql_volume: Volume, fqdn: str,
                 *, image=None, log_callback=None):
        nodes = location.ranked_nodes()

        # spawn database
        self.db = Postgresql(nodes[0], sql_volume, log_callback=log_callback)

        # spawn one webserver instance
        first_server = nodes[0].spawn_container('tfnz/silverstripe' if image is None else image,
                                                volumes=[(volume, '/site')],
                                                sleep=True,
                                                stdout_callback=log_callback)

        # see if the data volume has been initialised
        try:
            first_server.fetch("/site/index.php")
        except ValueError as e:
            # need to initialise - /site is visible on all servers
            logging.info("Initialising data volume: " + volume.uuid.decode())
            first_server.run_process('cp -r /silverstripe/* /site/')

        # recreate the .env because the database ip and password will have changed
        dotenv = SilverStripe.environment_template % (fqdn, self.db.password, self.db.private_ip())
        first_server.put('/site/.env', dotenv.encode())

        # start additional webservers
        self.webservers = [first_server]
        for node in nodes[1:]:
            server = node.spawn_container('tfnz/silverstripe',
                                          volumes=[(volume, '/site')],
                                          sleep=True)
            self.webservers.append(server)

        # start the actual webserving process
        fqdn_sed = "sed -i -e 's/--fqdn--/%s/g' /etc/nginx/conf.d/nginx.conf" % fqdn
        timezone_sed = "sed -i -e 's/;date.timezone =/date.timezone = %s/g' /etc/php7/php.ini" % "UTC"  # TODO
        pool_sed = "sed -i -e 's/pm.max_children = 5/pm.max_children = 16/g' /etc/php7/php-fpm.d/www.conf"
        for w in self.webservers:
            self.db.allow_connection_from(w)
            w.run_process('rm /etc/nginx/conf.d/default.conf /site/install*')
            w.run_process(fqdn_sed)
            w.run_process(timezone_sed)
            w.run_process(pool_sed)
            w.run_process('mkdir /run/nginx')
            w.spawn_process('nginx')
            w.spawn_process('php-fpm7')

        # gather together and serve into an endpoint
        self.cluster = Cluster(self.webservers)
        location.endpoint_for(fqdn).publish(self.cluster, fqdn)

        # wait until we're actually able to serve
        self.db.wait_until_ready()
        WebEndpoint.wait_http_200(fqdn)
        logging.info("SilverStripe is up.")

        # Start tailing logs
        for w in self.webservers:
            w.spawn_process('tail -f /var/log/nginx/access.log', data_callback=log_callback)
            w.spawn_process('tail -f /var/log/nginx/error.log', data_callback=log_callback)

    environment_template = """
SS_BASE_URL="http://%s"
SS_DATABASE_CLASS="PostgreSQLDatabase"
SS_DATABASE_NAME="SS_mysite"
SS_DATABASE_PASSWORD="%s"
SS_DATABASE_PORT="5432"
SS_DATABASE_SERVER="%s"
SS_DATABASE_USERNAME="postgres"
SS_DEFAULT_ADMIN_USERNAME="admin"
SS_DEFAULT_ADMIN_PASSWORD="password"
"""
