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
import socket
import os
import os.path
import paramiko
import paramiko.rsakey
import paramiko.ssh_exception
import logging
import shortuuid
import re
from threading import Thread
from .sftp import Sftp
from . import Waitable
from .tunnel import Tunnel


class SshServer(Waitable):
    """An SSH server using 20ft SDK calls.
    Username/password are whatever you want.
    Note that for the purposes of this, tunnels are regarded as processes because it makes loads of things simpler.

    Do not instantiate directly, use container.create_ssh_server"""

    def __init__(self, container, port):
        Waitable.__init__(self)
        self.uuid = shortuuid.uuid()
        self.container = weakref.ref(container)
        self.node = weakref.ref(container.parent())
        self.location = weakref.ref(self.node().parent())
        self.port = port
        self.run_thread = None
        self.stopping = False
        self.transports = {}  # id to object

        # get a host key
        host_key_fname = os.path.expanduser('~/.20ft/host_key')
        try:
            self.host_key = paramiko.RSAKey.from_private_key_file(host_key_fname)
        except FileNotFoundError:
            self.host_key = paramiko.rsakey.RSAKey.generate(1024)
            self.host_key.write_private_key_file(host_key_fname)

        # see if we can bring the socket up
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', self.port))

        # we are good to go
        self.sock.listen()
        logging.info("SSH server listening: ssh -p %s root@localhost" % self.port)

    def start(self):
        # creates the run loop on a separate thread
        self.run_thread = Thread(target=self.run, name="SSH server onto: " + self.container().uuid.decode())
        self.run_thread.start()
        self.mark_as_ready()

    def stop(self):
        # close the transports
        for transport in list(self.transports.values()):
            transport.stop()

        # close our own accept loop
        self.stopping = True
        self.run_thread.join()
        self.sock.close()

    def run(self):
        # an accept loop
        self.sock.settimeout(0.5)  # so we can poll for self.stopping
        while not self.stopping:
            try:
                # accept a new connection or poll
                try:
                    client, addr = self.sock.accept()
                except socket.timeout:
                    continue

                # wrap a transport round it
                transport = SshTransport(self, client, self.host_key)
                self.transports[transport.uuid] = transport

            except EOFError:
                raise ValueError("There was a problem with ssh - Is there an old key in 'known_hosts'?")

        logging.debug("Exiting server accept loop")

    def transport_closed(self, transport):
        logging.debug("SSH server knows transport has closed: " + transport.uuid)
        del self.transports[transport.uuid]

    def __repr__(self):
        return "<SshServer '%s' container=%s port=%d>" % \
               (self.uuid, self.container().uuid.decode(), self.port)


class SshTransport(paramiko.ServerInterface):
    """A Transport is the per-client abstraction, it will spawn channels."""

    def __init__(self, parent, socket, host_key):
        self.uuid = shortuuid.uuid()
        self.parent = weakref.ref(parent)
        self.container = weakref.ref(parent.container())
        self.lead_channel = None
        self.socket = socket
        self.paramiko_transport = paramiko.Transport(socket)
        self.paramiko_transport.add_server_key(host_key)
        self.paramiko_transport.set_subsystem_handler('sftp', paramiko.SFTPServer, Sftp)
        self.paramiko_transport.start_server(server=self)  # for this one connection

        # channels and port forwarding
        self.channels = {}  # ssh channel id to SshChannel
        self.reverses = {}  # port to SshReverse

        # tunnels are requested before the channel is open
        self.pending_tunnels = {}  # ssh channel id to list of port numbers
        self.pending_reverses = []  # a list of reverse objects

        # start the transport's accept loop
        self.accept_thread = Thread(target=self.channel_accept, name="SSH transport: " + self.uuid)
        self.accept_thread.start()

    def channel_accept(self):
        # a per-transport accept loop
        close_callback = self.stop
        while True:
            channel = self.paramiko_transport.accept()

            # is the transport closing down?
            if channel is None:
                break  # breaks the loop

            # otherwise we're all good
            chid = channel.get_id()
            logging.debug("Accepted paramiko channel: " + str(chid))
            ssh_channel = SshChannel(channel, self.container(), close_callback)
            if close_callback is not None:  # is the leader channel
                self.lead_channel = ssh_channel
            self.channels[chid] = ssh_channel
            close_callback = None

            # waiting to spawn forward tunnels?
            if chid in self.pending_tunnels:
                for port in self.pending_tunnels[chid]:
                    logging.debug("Spawning pending forward for port: " + str(port))
                    ssh_channel.spawn_tunnel(port)  # can only happen after .accept has happened
                del self.pending_tunnels[chid]

            # waiting to spawn channels for reverse tunnels?
            # keeps track of it's own child tunnels
            for reverse in self.pending_reverses:
                try:
                    logging.debug("Hooking up pending reverse for port: " + str(reverse.dest_addr[1]))
                    reverse.spawn_channel()
                    self.reverses[reverse.dest_addr[1]] = reverse
                except ValueError as e:
                    logging.warning(e)
            self.pending_reverses.clear()

        # exited the loop
        logging.debug("Transport loop exited for: " + self.uuid)

        # let the parent know we're done
        self.parent().transport_closed(self)

    def stop(self):
        if self.socket is None:
            return

        # do reverses first because they will hold open processes in sessions
        for reverse in list(self.reverses.values()):
            reverse.close()
        for channel in list(self.channels.values()):
            channel.close_callback = None
            channel.close()

        # close down the transport
        self.accept_thread.join()
        self.paramiko_transport.close()
        self.socket = None
        logging.debug("Transport closed for: " + self.uuid)

    # Paramiko authentication (or lack thereof)
    def check_auth_none(self, username):
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return 'none'

    def check_channel_request(self, kind, chanid):
        logging.debug("SSH channel_request (%s): %d" % (kind, chanid))
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    # Tunnel requests (-L) are requested before the channel is opened
    # We keep track of what we agreed to and open the forwarding requests once the channel has been accepted
    def check_channel_direct_tcpip_request(self, chanid, origin, destination):
        if chanid in self.channels:
            logging.info("SSH direct_tcpip_request received on open channel, just returning 'succeeded'")
        else:
            logging.info("SSH direct_tcpip_request waiting on port: " + str(destination[1]))
            if chanid not in self.pending_tunnels:
                self.pending_tunnels[chanid] = []
            self.pending_tunnels[chanid].append(destination[1])
        return paramiko.OPEN_SUCCEEDED

    # These are the reverse forwarding requests (-R)
    # You need to open a channel back to the client but the channel from the client needs to have been opened first
    # hence we just keep track of this, say "yes" and then wait for the client channel to be accepted.
    # it doesn't work to check for the reverse being open at this point because it could be, under another transport
    def check_port_forward_request(self, address, port):
        logging.info("SSH port_forward_request (reverse): %s:%d" % (address, port))
        self.pending_reverses.append(SshReverse((address, port), self.container(), self))
        return port

    # Callbacks across the server interface
    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        # an occasional race condition
        while not channel.get_id() in self.channels:
            os.sched_yield()
        self.channels[channel.get_id()].set_pty_dimensions(width, height)
        return True

    def check_channel_window_change_request(self, channel, width, height, pixelwidth, pixelheight):
        # gets called if window changes size while server is active
        self.channels[channel.get_id()].set_pty_dimensions(width, height)
        self.channels[channel.get_id()].send_window_change()
        return True

    def check_channel_exec_request(self, channel, command):
        while not channel.get_id() in self.channels:
            os.sched_yield()
        return self.channels[channel.get_id()].spawn_process(command)

    def check_channel_shell_request(self, channel):
        while not channel.get_id() in self.channels:
            os.sched_yield()
        return self.channels[channel.get_id()].spawn_shell()


class SshChannel:
    """A channel is a single channel through a transport. It can be connected to only one process."""

    def __init__(self, paramiko_channel, container, close_callback=None):
        self.paramiko_channel = paramiko_channel
        self.container = weakref.ref(container)
        self.connection = weakref.ref(container.conn())
        self.node = weakref.ref(container.parent())
        self.location = weakref.ref(self.node().parent())
        self.loop = weakref.ref(self.connection().loop)
        self.width = 80
        self.height = 24
        self.process = None  # only one process
        self.close_callback = close_callback

    def close(self, obj=None, returncode=0):  # signature needs to be this for callback to work
        # if we've been closed already, just skip out
        if self.paramiko_channel is None:
            return

        # has this been created with a callback?
        if self.close_callback is not None:
            logging.debug("Closing lead channel.")
            cc = self.close_callback
            self.close_callback = None
            cc()
            return

        # close the channel
        chid = self.paramiko_channel.get_id()
        fd = self.paramiko_channel.fileno()
        logging.debug("[chan %d] closing" % chid)

        self.paramiko_channel.send_exit_status(returncode)
        self.paramiko_channel.shutdown(2)
        self.paramiko_channel.close()
        self.paramiko_channel = None
        if fd in self.loop().exclusive_handlers:
            self.loop().unregister_exclusive(fd)

        # close the process (they aren't tied into the container in this case)
        if self.process is not None:
            if self.process.uuid in self.location().tunnels:
                del self.location().tunnels[self.process.uuid]
            if not self.process.dead:
                self.process.destroy()

    def get_id(self):
        return self.paramiko_channel.get_id()

    # events coming in from the transport

    def set_pty_dimensions(self, width, height):
        self.width = width
        self.height = height

    def send_window_change(self):
        # send the window change event
        self.connection().send_cmd(b'tty_window', {'node': self.node().pk,
                                                   'container': self.container().uuid,
                                                   'process': self.process.uuid,
                                                   'width': self.width,
                                                   'height': self.height})

    def spawn_process(self, command):
        # spawn the process on the end of this channel
        self.process = self.container().spawn_process(command.decode(),
                                                      data_callback=self.data,
                                                      stderr_callback=self.stderr,
                                                      termination_callback=self.close)
        self.loop().register_exclusive(self.paramiko_channel.fileno(), self.event,
                                       comment="SSH Process " + self.process.uuid.decode())
        return True

    def spawn_shell(self):
        # spawn the process on the end of this channel
        self.process = self.container().spawn_shell(data_callback=self.data,
                                                    termination_callback=self.close,
                                                    echo=True)
        self.loop().register_exclusive(self.paramiko_channel.fileno(), self.event,
                                       comment="SSH Shell " + self.process.uuid.decode())
        self.send_window_change()
        return True

    def spawn_tunnel(self, port):
        logging.debug("Spawning forwarding tunnel for port: " + str(port))
        tunnel = Tunnel(self.connection(), self.node(), self.container(), port)
        tunnel.connect_tcpip_direct(self)  # gets the tunnel to send the data here instead of creating tcp sockets
        self.process = tunnel
        self.location().tunnels[tunnel.uuid] = tunnel  # needs this so 'close proxy' events are handled properly
        self.loop().register_exclusive(self.paramiko_channel.fileno(), self.event,
                                       comment="SSH Tunnel " + self.process.uuid.decode())

    # flows

    def data(self, obj, data):
        # from remote
        # if len(data) > 3:
        #     logging.debug("[chan %d] <== %s" % (self.paramiko_channel.get_id(), data.decode()))
        try:
            self.paramiko_channel.sendall(data)
        except OSError:
            logging.debug("[chan %d] Failed to send: %s" % (self.paramiko_channel.get_id(), data.decode()))

    def stderr(self, obj, data):
        logging.debug("[chan %d - stderr] <== %s" % (self.paramiko_channel.get_id(), data.decode()))
        try:
            self.paramiko_channel.sendall_stderr(data)
        except OSError:
            logging.debug("[chan %d - stderr] Failed to send: %s" % (self.paramiko_channel.get_id(), data.decode()))

    def event(self, fd):
        # A file descriptor is triggered on 'our' side
        while self.paramiko_channel.recv_ready():
            data = self.paramiko_channel.recv(8192)  # fits inside a jumbo frame at the other end
            # if len(data) > 3:
            #     logging.debug("[chan %d] ==> %s" % (self.paramiko_channel.get_id(), data.decode()))
            self.process.stdin(data)


class SshReverse:
    socat_re = re.compile(b'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} socat')

    def __init__(self, dest_addr, container, transport):
        # init
        self.dest_addr = dest_addr
        self.container = weakref.ref(container)
        self.transport = weakref.ref(transport)  # needed for open_forwarded_tcpip_channel
        self.process_channel = {}
        self.listening_process = self.spawn_socat()

    def spawn_socat(self):
        # spawn the process that will receive connections inside the container
        logging.debug("Spawning remote listener process for port: " + str(self.dest_addr[1]))
        proc = 'socat -ls -d -d TCP4-LISTEN:%d,reuseaddr STDIO' % self.dest_addr[1]
        return self.container().spawn_process(proc,
                                              data_callback=self.data,
                                              termination_callback=self.terminated,
                                              stderr_callback=self.stderr)

    def spawn_channel(self):
        # does the channel exist already? (set up as part of pending)
        if self.listening_process in self.process_channel:
            return

        # is this a broken reverse?
        if self.listening_process is None:
            self.fail_words("Cannot spawn channel because port is already being listened: " + str(self.dest_addr[1]))
            return

        # when paramiko has finished doing it's thing, we can spawn a forwarded channel
        src_addr = ('127.0.0.1', self.dest_addr[1])
        try:
            p_channel = self.transport().paramiko_transport.open_forwarded_tcpip_channel(src_addr, self.dest_addr)
        except paramiko.ssh_exception.ChannelException:
            self.fail_words("Failed to connect reverse channel onto port: " + str(self.dest_addr[1]))
            return
        channel = SshChannel(p_channel, self.container())

        # hook into the message loop
        try:
            channel.loop().register_exclusive(p_channel.fileno(),
                                              channel.event,  # sent directly from channel, does not filter through here
                                              comment="SSH Reverse " + self.listening_process.uuid.decode())
        except RuntimeError:
            self.fail_words("Tried to register exclusive twice, closing channel: " + str(p_channel.get_id()))
            channel.close(self, 1)
            return

        # hook up indexes
        self.process_channel[self.listening_process] = channel
        channel.process = self.listening_process
        logging.debug("[chan %d] opened to port: %d" % (channel.get_id(), self.dest_addr[1]))
        return channel

    def terminated(self, process, returncode):
        # single terminated process
        logging.debug("SshReverse process terminated: %s (%d)" % (process.uuid.decode(), returncode))

        # may be an established channel, not just the listening process
        try:
            channel = self.process_channel[process]
            channel.close(process, returncode)
            del self.process_channel[process]
        except KeyError:
            logging.debug("...did not have an associated channel")

    def close(self):
        logging.debug("Closing processes for SSH reverse tunnel on port: " + str(self.dest_addr[1]))
        for process in list(self.process_channel.keys()):
            process.destroy()
        if self.listening_process is not None:
            self.listening_process.destroy()

    # Data from the actual process
    def data(self, process, data):
        self.process_channel[process].data(process, data)

    # When socat accepts the connection, we need to create it on this side
    def stderr(self, process, data):

        # see if this is normal stderr
        if SshReverse.socat_re.match(data) is None:
            self.process_channel[process].stderr(process, data)
            return

        # we caught something from socat
        logging.debug("(socat) " + data.decode()[:-1])
        if b'accepting connection from' in data:
            self.spawn_channel()
            self.listening_process = self.spawn_socat()  # spawn another listener
            return

        if b'Address already in use' in data:
            # going to let process termination actually cause the whole thing to shut down
            self.fail_words('Cannot open forwarding channel, port is in use: ' + str(self.dest_addr[1]))
            return

    def fail_words(self, words):
        # echo the failure message down the ssh session's lead channel if possible
        self.transport().lead_channel.stderr(self, words.encode() + b'\r\n')
        logging.warning(words)
