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
from tfnz.location import Location
from tfnz.volume import Volume

dkim_template = '''
    dkim_domain = %s
    dkim_selector = %s
    dkim_private_key = /var/mail/dkim.key.pem
'''


class Mail:
    def __init__(self, domain_name: str, recipients: [str], *, ssh: bool=False, image: str=None, dkim: bool=False):
        """Instantiate a mail server object.
        If dkim=True, will log the necessary records to be added to DNS
        The certificate and key are given as strings (not filenames).
        The one you use for the webserver is fine if it doesn't say 'www' on it.

        :param domain_name: The domain name to serve.
        :param recipients: A list of recipients in "username:password" strings.
        :param ssh: Create an ssh server for debugging on port 2222.
        :param image: Use a container image other than tfnz/mail.
        :param dkim: Sign outgoing emails.
        :return: A dict representation of image metadata."""
        # check the recipients are in name:pass format
        recipient_re = re.compile('\A[a-zA-Z0-9_.+-]+:\S+\Z')
        self.recipients = [r.strip('\n') for r in recipients]
        if len(self.recipients) == 0:
            raise ValueError("Mail needs to be passed at least one recipient")
        for recipient in self.recipients:
            if recipient_re.match(recipient) is None:
                raise ValueError("Email addresses should be in a 'username:password' format")
        if domain_name is None or len(domain_name) == 0:
            raise ValueError("Exim needs a domain name to function (try 'local'?)")
        self.domain_name = domain_name
        self.ssh = ssh
        self.server_condition = '${if !eq{$tls_cipher}{}}'  # nasty hack to get around .format trying to expand it
        self.system_aliases_data= '${lookup{$local_part}lsearch{/etc/aliases}}'
        self.dkim = dkim
        self.dkim_text = ''
        self.image = 'tfnz/mail' if image is None else image

    def spawn(self, location: Location, volume: Volume, *, log_callback=None,
              local_smtp=25, local_smtps=465, local_imap=993):
        """Instantiate the mail server container.
        Anything with a username/password has to go over SSL. So port 25 is only for mail delivery, not relay.

        :param location: A location (object) to connect to.
        :param volume: A volume (object) to use as a persistent store.
        :param log_callback: An optional callback for log messages -  - signature (object, bytes)
        :param local_smtp: TCP port to open locally for smtp traffic - can only be used for delivery.
        :param local_smtps: TCP port to open locally for smtp (with SSL) traffic.
        :param local_imap: TCP port to open locally for IMAP (with SSL).
        """
        # create the container
        node = location.node()
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

        # set hostname
        container.run_process('hostname mail')

        # create user accounts
        passwd_file = ''
        first_recipient = None
        for recipient in self.recipients:
            username, password = recipient.split(':')
            if first_recipient is None:
                first_recipient = username
            pw = container.run_process('doveadm pw -u %s -p %s' % (username, password))[0][:-1]
            passwd_file += '%s:%s:90:101\n' % (username, pw.decode())
        container.put('/etc/dovecot/passwd', passwd_file.encode())

        # create system aliases - uses the first recipient as the destination
        aliases = ['root', 'postmaster', 'hostmaster', 'mail', 'admin', 'abuse',
                   'webmaster', 'mailer-daemon', 'nobody', 'www', 'security']
        alias_file = ''
        for alias in aliases:
            alias_file += '%s: %s\n' % (alias, first_recipient)
        container.put('/etc/aliases', alias_file.encode())

        # render the exim configuration
        exim_template = container.fetch('/home/admin/exim_template').decode()
        container.put('/etc/exim/exim.conf', exim_template.format(self).encode())

        # attach an SMTP tunnel and run exim
        container.spawn_process('tail -f /var/log/exim/mainlog', data_callback=log_callback)
        container.attach_tunnel(25, localport=local_smtp)
        container.attach_tunnel(465, localport=local_smtps)
        container.spawn_process('/usr/sbin/exim -bdf -q30m', data_callback=log_callback)

        # same again with dovecot
        container.attach_tunnel(993, localport=local_imap)
        container.spawn_process('/usr/sbin/dovecot', data_callback=log_callback)
