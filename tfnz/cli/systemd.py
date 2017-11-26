"""
Copyright (c) 2017 David Preece, All rights reserved.

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

# creating a systemd service
from subprocess import check_call


# removes a flagged parameter from argv
# note: mutates argv
def remove_flagged(param, argv):
    flag_find = [a for a in enumerate(argv) if a[1] == param]
    if len(flag_find) == 1:
        del argv[flag_find[0][0]]  # flag
        del argv[flag_find[0][0]]  # and the value


def systemd(location, args, argv, preboot):
    # note that this is *knee* *deep* in potential security holes but since it is connecting to
    # a non-multi-tenanted server under the user's control I'm not all that bothered about it.
    # you were warned

    # checks
    if '/' not in args.source:
        print("Use a tagged image (i.e. my/example) to create a service")
        return 1
    if '@' not in args.systemd:
        print("Please use a user@server ssh connection string.")
    username = args.systemd.split('@')[0]

    # build the ssh command line
    if args.identity is None:
        ssh = ['ssh', args.systemd]
        sftp = 'sftp %s' % args.systemd
    else:
        ssh = ['ssh', '-i', args.identity, args.systemd]
        sftp = 'sftp -i %s %s' % (args.identity, args.systemd)

    # ensure file structure on the receiving machine
    service_name = args.source.replace('/', '-')
    path = '/home/%s/%s/' % (username, service_name)
    check_call(ssh + ['mkdir', '-p', path])

    # ensure the image is uploaded to the *location* (not a per-client server)
    location.ensure_image_uploaded(args.source)

    # write any preboot files
    for source, _ in preboot:
        check_call('echo "put %s" | %s:%s' % (source, sftp, path), shell=True)

    # remove the procname, --systemd and --identity from argv
    del argv[0]
    remove_flagged('--systemd', argv)
    remove_flagged('--identity', argv)

    # render the unit file
    filename = service_name + '.service'
    with open(filename, 'w') as f:
        f.write('''
[Unit]
Description=20ft-%s

[Service]
Type=simple
ExecStart=/usr/local/bin/tf %s
WorkingDirectory=%s
KillSignal=SIGINT
TimeoutStopSec=5
Restart=always
User=%s
Group=%s

[Install]
WantedBy=multi-user.target
    ''' % (args.source, ' '.join(argv), path, username, username))
    check_call('echo "put %s" | %s:%s' % (filename, sftp, path), shell=True)
    check_call(['rm', filename])

    # let systemd know
    check_call(ssh + ['sudo', 'ln', '-s', path + filename, '/etc/systemd/system/'])
    check_call(ssh + ['sudo', 'systemctl', 'enable', service_name])
    check_call(ssh + ['sudo', 'systemctl', 'daemon-reload'])
    check_call(ssh + ['sudo', 'systemctl', 'start', service_name])
    return 0