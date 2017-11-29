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


class Mail:
    def __init__(self, domain_name: str, recipients: [str]):
        # check the recipients are in name:pass format
        recipient_re = re.compile('\A[a-zA-Z0-9_.+-]+:\S+\Z')
        for recipient in recipients:
            if recipient_re.match(recipient) is None:
                raise ValueError("Email addresses should be in a 'username:password' format")
        self.recipients = recipients
        if domain_name is None or len(domain_name) == 0:
            raise ValueError("Exim needs a domain name to function (try 'local'?)")
        self.domain_name = domain_name

    def go(self, location: Location, volume_tag: str, log_callback=None):
        # render the config file
        exim_config_template = '''
primary_hostname = {0.domain_name}
qualify_domain = {0.domain_name}
domainlist local_domains = {0.domain_name}
hostlist relay_from_hosts = 10.0.0.0/8

prdr_enable = true
ignore_bounce_errors_after = 2d
timeout_frozen_after = 7d
acl_smtp_rcpt = acl_check_rcpt
acl_smtp_data = acl_check_data

begin acl
acl_check_rcpt:
    accept  hosts = :
            control = dkim_disable_verify
    accept  local_parts   = postmaster
            domains       = +local_domains
    require verify        = sender
    accept  hosts         = +relay_from_hosts
            control       = submission
            control       = dkim_disable_verify      
    require message = relay not permitted
            domains = +local_domains : +relay_to_domains  
    require verify = recipient
    # deny    message       = rejected because $sender_host_address is in a black list at bl.spamcop.net
    #         dnslists      = bl.spamcop.net
    accept
    
acl_check_data:
    accept
    
begin routers
dnslookup:
    driver = dnslookup
    domains = ! +local_domains
    transport = remote_smtp
    ignore_target_hosts = 0.0.0.0 : 127.0.0.0/8
    no_more
  
localuser:
    driver = accept
    check_local_user
    local_part_suffix = +* : -*
    local_part_suffix_optional
    transport = local_delivery
    cannot_route_message = Unknown user
    
begin transports

remote_smtp:
    driver = smtp
    
local_delivery:
    driver = appendfile
    file = /var/mail/$local_part
    delivery_date_add
    envelope_to_add
    return_path_add
  
begin retry
    *                      *           F,2h,15m; G,16h,1h,1.5; F,4d,6h
    
# begin authenticators
# LOGIN:
#     driver                     = plaintext
#     server_set_id              = $auth1
#     server_prompts             = <| Username: | Password:
#     server_condition           = Authentication is not yet configured
        '''

        # create the container
        node = location.ranked_nodes(RankBias.memory)[0]
        container = node.spawn_container('tfnz/mail',
                        pre_boot_files=[('/etc/exim/exim.conf', exim_config_template.format(self))],
                        termination_callback=location.disconnect,
                        sleep=True)
        container.wait_until_ready()

        # create user accounts
        for recipient in self.recipients:
            container.run_process('adduser -D ' + recipient.split(':')[0])
            container.run_process('echo "%s" | chpasswd' % recipient)

        # attach an SMTP tunnel and run exim
        container.attach_tunnel(25, localport=2525)
        container.spawn_process('/usr/sbin/exim -bdf')
        container.spawn_process('tail -f /var/log/exim/mainlog', data_callback=log_callback)
