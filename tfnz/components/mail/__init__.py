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
from datetime import date
from tfnz.location import Location, RankBias
from tfnz.volume import Volume

dkim_template = '''
    dkim_domain = %s
    dkim_selector = %s
    dkim_private_key = /var/mail/dkim.key.pem
'''


class Mail:
    def __init__(self, domain_name: str, recipients: [str], *, dkim=False, ssh=False, image=None):
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
        self.server_condition = '${if !eq{$tls_cipher}{}}'  # nasty hack to get around .format trying to expand it
        self.dkim = dkim
        self.dkim_text = ''
        self.image = 'tfnz/mail' if image is None else image

    def go(self, location: Location, volume: Volume, *, log_callback=None,
           local_smtp=25, local_smtps=465, local_imap=993):
        # create the container
        node = location.ranked_nodes(RankBias.memory)[0]
        container = node.spawn_container(self.image,
                                         volumes=[(volume, '/var/mail')],
                                         termination_callback=location.disconnect,
                                         sleep=True).wait_until_ready()

        # maybe an ssh window
        if self.ssh:
            container.create_ssh_server()

        # create certs if not there
        if b'server.pem' not in container.run_process('ls /var/mail')[0]:
            container.run_process('openssl req -x509 -newkey rsa:1024 -sha256 '
                                  '-keyout /var/mail/server.key -out /var/mail/server.pem -nodes -days 9999 '
                                  '-subj \'/CN=%s\'' % self.domain_name)

        if self.dkim:
            # same again for dkim
            if b'dkim.key.pem' not in container.run_process('ls /var/mail')[0]:
                container.run_process('openssl genrsa -out /var/mail/dkim.key.pem 1024 -outform PEM')
                container.run_process('openssl rsa -in /var/mail/dkim.key.pem'
                                      '            -out /var/mail/dkim.pub.pem -pubout -outform PEM')
                container.put('/var/mail/dkim_selector', date.today().strftime('%Y%M%d').encode())

            # render the dkim configuration
            dkim_selector = container.fetch('/var/mail/dkim_selector')
            dkim_pk = container.fetch('/var/mail/dkim.pub.pem')
            self.dkim_text = dkim_template % (self.domain_name, dkim_selector.decode())

            # log the DNS changes
            print("@ TXT \"v=spf1 a mx ip4:this.is.mx.ip\"")
            print("%s._domainkey TXT \"v=DKIM1; p=%s\"" %
                  (dkim_selector.decode(), dkim_pk.decode()[27:-26].replace('\n', '')))

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
        container.attach_tunnel(465, localport=local_smtps)
        container.spawn_process('/usr/sbin/exim -bdf', data_callback=log_callback)  # creates the exim user

        # same again with dovecot
        container.attach_tunnel(993, localport=local_imap)
        container.spawn_process('/usr/sbin/dovecot', data_callback=log_callback)
