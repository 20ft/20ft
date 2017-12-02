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
import re
from tfnz.location import Location, RankBias
from tfnz.volume import Volume


class Mail:
    def __init__(self, domain_name: str, recipients: [str], ssh=False):
        # check the recipients are in name:pass format
        recipient_re = re.compile('\A[a-zA-Z0-9_.+-]+:\S+\Z')
        self.recipients = [r.strip('\n') for r in recipients]
        for recipient in self.recipients:
            if recipient_re.match(recipient) is None:
                raise ValueError("Email addresses should be in a 'username:password' format")
        if domain_name is None or len(domain_name) == 0:
            raise ValueError("Exim needs a domain name to function (try 'local'?)")
        self.domain_name = domain_name
        self.ssh = ssh

    def go(self, location: Location, volume: Volume, *, log_callback=None, local_smtp=25, local_imap=993):
        # create the container
        node = location.ranked_nodes(RankBias.memory)[0]
        container = node.spawn_container('tfnz/mail',
                                         volumes=[(volume, '/var/mail')],
                                         termination_callback=location.disconnect,
                                         sleep=True).wait_until_ready()

        # maybe an ssh window
        if self.ssh:
            container.create_ssh_server()

        # create certs if not there
        if b'server.pem' not in container.run_process('ls /var/mail')[0]:
            container.run_process('openssl req -x509 -newkey rsa:1024 -sha256 '
                                  '-keyout /var/mail/server.key -out /var/mail/server.pem -nodes -days 365 '
                                  '-subj \'/CN=%s\'' % self.domain_name)

        # create user accounts
        passwd_file = b''
        for recipient in self.recipients:
            username, password = recipient.split(':')
            pw = container.run_process('doveadm pw -u %s -p %s' % (username, password))[0][:-1]
            pwl = '%s:%s:90:101\n' % (username, pw.decode())
            passwd_file += pwl.encode()
        container.put('/etc/dovecot/passwd', passwd_file)

        # render the exim configuration
        exim_template = container.fetch('/home/admin/exim_template').decode()
        container.put('/etc/exim/exim.conf', exim_template.format(self).encode())

        # attach an SMTP tunnel and run exim
        container.spawn_process('tail -f /var/log/exim/mainlog', data_callback=log_callback)
        container.attach_tunnel(25, localport=local_smtp)
        container.spawn_process('/usr/sbin/exim -bdf', data_callback=log_callback)  # creates the exim user

        # same again with dovecot
        container.spawn_process('tail -f /var/log/dovecot.log', data_callback=log_callback)
        container.attach_tunnel(993, localport=local_imap)
        container.spawn_process('/usr/sbin/dovecot', data_callback=log_callback)
