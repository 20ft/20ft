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
import _thread
import socket
import os.path
import paramiko
import paramiko.rsakey
import logging
from .sftp import Sftp
from . import Waitable


class Ssh(paramiko.ServerInterface, Waitable):
    """Wrapping a call to 'spawn process' in an ssh shell
    Username/password are whatever you want.

    Do not instantiate directly, use container.create_ssh_server"""
    def __init__(self, container, port):
        paramiko.ServerInterface.__init__(self)
        Waitable.__init__(self)
        self.container = weakref.ref(container)
        self.port = port
        self.channel_init = {}
        self.fd_process = {}
        self.process_channel = {}
        self.channel_process = {}

        # get a host key
        host_key_fname = os.path.expanduser('~/.20ft/host_key')
        try:
            self.host_key = paramiko.RSAKey.from_private_key_file(host_key_fname)
        except FileNotFoundError:
            self.host_key = paramiko.rsakey.RSAKey.generate(1024)
            self.host_key.write_private_key_file(host_key_fname)

        # a listen/accept loop
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(('', self.port))
        except OSError:
            raise RuntimeError("Tried to start ssh server but the port was already taken: " + str(self.port))

    def start(self):
        # creates the run loop on a separate thread
        _thread.start_new_thread(self.run, ())
        self.wait_until_ready()

    ########### Paramiko authentication (bypassing thereof)
    def check_auth_none(self, username):
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return 'none'

    ########## Paramiko callbacks
    def check_channel_request(self, kind, chanid):
        logging.debug("SSH check_channel_request (%s): %d" % (kind, chanid))
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        logging.debug("SSH check_channel_pty_request (%s): %d" % (term, channel.get_id()))
        self.channel_init[channel] = (width, height)
        return True

    def check_channel_window_change_request(self, channel, width, height, pixelwidth, pixelheight):
        # gets called if window changes size while server is active
        process = self.channel_process[channel]
        self._send_window_change(process.uuid, width, height)
        return True

    def check_channel_exec_request(self, channel, command):
        # Yes, we can exec directly down the channel (run on another thread)
        _thread.start_new_thread(self._implement_exec_request, (channel, command.decode()))
        return True

    def check_channel_shell_request(self, channel):
        logging.info("SSH shell_request: " + str(channel))
        # spawning a shell, but we do know the window size
        process = self.container().spawn_shell(data_callback=self.data,
                                               termination_callback=self.terminated,
                                               echo=True)
        dims = self.channel_init[channel]  # the dimensions of the window when check_channel_pty_request
        self._send_window_change(process.uuid, dims[0], dims[1])
        del self.channel_init[channel]
        self._create_indexes(channel, process)
        return True

    def check_port_forward_request(self, address, port):
        # forwarding for debuggers
        self.container().attach_tunnel(port)
        return True

    ######### Controller
    def run(self):
        while True:
            self.sock.listen()
            logging.info("SSH server listening: ssh -p %s root@localhost" % self.port)
            self.mark_as_ready()
            try:
                client, addr = self.sock.accept()

                # wrap a transport round it
                transport = paramiko.Transport(client)
                transport.add_server_key(self.host_key)
                transport.set_subsystem_handler('sftp', paramiko.SFTPServer, Sftp)
                transport.start_server(server=self)  # for authentication

                # wait for authentication
                # if you take 'channel=' off it completely fails. no idea why.
                channel = transport.accept()

            except EOFError:
                raise ValueError("There was a problem with ssh - Is there an old key in 'known_hosts'?")

    def terminated(self, obj):
        channel = self.process_channel[obj]
        fd = channel.fileno()
        self.container().conn().loop.unregister_exclusive(fd)
        channel.send_exit_status(0)
        channel.close()
        del self.fd_process[fd]
        del self.process_channel[obj]
        del self.channel_process[channel]

    def data(self, obj, data):
        # from 'their' side
        try:
            channel = self.process_channel[obj]
            channel.sendall(data)
        except (OSError, KeyError):
            logging.debug("A bad thing")

    def event(self, skt):
        # from 'our' side
        process = self.fd_process[skt]
        channel = self.process_channel[process]
        data = channel.recv(16384)
        process.stdin(data)

    def _create_indexes(self, channel, process):
        self.fd_process[channel.fileno()] = process
        self.process_channel[process] = channel
        self.channel_process[channel] = process

        # tie into the loop last because this will cause events to happen
        self.container().conn().loop.register_exclusive(channel.fileno(), self.event,
                                                        comment="From ssh chan: " + str(channel))
        return True

    def _send_window_change(self, uuid, width, height):
        self.container().conn().send_cmd(b'tty_window', {'node': self.container().parent().pk,
                                                         'container': self.container().uuid,
                                                         'process': uuid,
                                                         'width': width,
                                                         'height': height})

    def _implement_exec_request(self, channel, command):
        # An explicitly started remote command (on a separate thread)
        logging.info("SSH direct exec_request: %s..." % command[:20])
        stdout, stderr, exit_code = self.container().run_process(command)
        channel.sendall(stdout)
        channel.sendall_stderr(stderr)
        channel.send_exit_status(exit_code)
        channel.close()
        logging.debug("exec_request exited: %s..." % command[:20])
