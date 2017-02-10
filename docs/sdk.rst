====================
20ft.nz Python 3 SDK
====================

The vast majority of power in 20ft is contained in the Python SDK. The SDK is BSD licensed so feel free to modify, extend and distribute either the SDK or applications based on it (including commercial applications) without either fee or attribution. The ``tf`` command is also covered by the license.

It is designed to enable the simple construction of orchestration applications including (but not limited to): unit testing; deployment and scaling; and unique container native architectures.

All the examples below are complete programs. They can be run by pasting the example into a text file (called, say, 'scratch.py') then running with ``python3 scratch.py``.

Architecture
============

There are four main actors in a 20ft session: The client, the location, the nodes and their containers.

..  glossary::
    Client
        A piece of software running the 20ft sdk. Clients need to connect outwards to the Internet on TCP port 5555 and must be able to resolve DNS.

    Location
        Effectively the "server" of a client server pair, the location acts as a secured message broker, an image server and a network manager. It needs TCP port 5555 to be open.

    Node
        The nodes can spawn containers and will update the Location with its current resource statistics.

    Container
        Once spawned, a container is provided with a non-routable ip and default gateway. Containers in the SDK can also create a TCP tunnel from localhost onto a port, fetch and place files, spawn processes and return logs.

Quickstart examples in Python
=============================

Let's start by implementing the "first container" and "Docker workflow" examples above::

   import signal
   from tfnz.location import Location

   location = Location(debug_log=False)
   node = location.best_node()
   container = node.spawn('nginx')
   container.attach_browser()
   signal.pause()

The Location object by default connects to the location in '~/.20ft/default_location', and this behaviour can be changed by merely passing the fqdn of an alternative on which you have an account - for instance Location('syd.20ft.nz'). debug_log is one of three values: None (the default) does nothing to the `user configured <https://docs.python.org/3/howto/logging.html#logging-basic-tutorial>`_  logging; False sets up Python debugging to the 'info' level (-v on tf); and True sets Python debugging to the 'debug' level (-vv on tf).

We have a 'last_image' function as part of the location module. So the Docker workflow example is::

   import signal
   from tfnz.location import Location, last_image

   location = Location(debug_log=False)
   node = location.best_node()
   container = node.spawn(last_image())
   container.attach_browser()
   signal.pause()

Controlling the end of execution (here using signal.pause) is important. Without it the script will exit and 20ft will remove all the created resources before you've had a chance to use them for anything. You probably don't want this.

Finally you can chain the return values together so you *could* write: ::

   import signal
   from tfnz.location import Location, last_image

   Location(debug_log=False).best_node().spawn(last_image()).attach_browser()
   signal.pause()

This has been avoided in this documentation for the sake of clarity.

Putting and Fetching files
==========================

It's important to note that a 20ft "fetch" or "put" relates to a single file and not an archive of an entire filesystem branch (you may have seen this in Docker). Also, while convenient, the file will be loaded into memory as an intermediate step so this is not a great way to send large files. Try... ::

    from tfnz.location import Location, last_image

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    container.put("/usr/new/path", b'Some data')
    print(container.fetch("/usr/new/path"))
    print("------------------------------------")
    print(str(container.fetch("/etc/nginx/nginx.conf"), 'ascii'))

As you can see, placing a file onto a new path causes the path to be created.

Creating TCP Tunnels
====================

TCP (only) tunnels can be created from localhost onto a container. The local port number can be either set or left blank (in which case it is chosen for you and becomes the ``.localport()`` method of the tunnel)... ::

    import signal
    from tfnz.location import Location

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    tnl = container.attach_tunnel(80, localport=1234)
    signal.pause()

A Special Case for Webservers
=============================

The above example is a generalised case TCP tunnel and can be used for web, ssh, smtp, whatever. There are also two specialised tunnel factories specifically for webservers: container.wait_http_200() and container.attach_browser(). The first case creates a tunnel as normal then blocks execution and polls the other end until it receives a reply with HTTP code 200. You can set a domain name for webapps that need a "Host:" header to be send, and a path to the resource to fetch can also be passed.

The second option does exactly the same thing except it also launches a web browser onto the newly created tunnel. ::

    import signal
    from tfnz.location import Location, last_image

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    tnl = container.attach_browser()
    signal.pause()

Launching Processes in Containers
=================================

"Container style" launch-at-boot of a single server process obviously doesn't cover all use cases so in 20ft it's possible to launch a process inside a pre-booted container. There can be multiple processes running concurrently and they can be run either synchronously to completion, or asynchronously with callbacks for the stdout stream and process termination. Some examples: Synchronously... ::

    from tfnz.location import Location

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    container.wait_http_200()
    data = container.spawn_process('ps faxu').wait_until_complete()
    print(data.decode())

Asynchronously... ::

    import time
    from tfnz.location import Location

    def dc(obj, data):
        print(data.decode(), end='')

    def tc(obj):
        print("vmstat terminated")

    def sleep_tc(obj):
        print("---sleep terminated---")

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    vmstat = container.spawn_process('vmstat 1', data_callback=dc, termination_callback=tc)
    sleep = container.spawn_process('sleep 3', termination_callback=sleep_tc)
    time.sleep(10)
    container.destroy_process(vmstat)  # just so we get the termination callback

Interacting with Processes
==========================

To interact with a long-lived process you can inject into the process's stdin stream. When running asynchronously, the callback technique above remains the same and we use ``process.stdin(b'whatever')`` to inject into the process. To run synchronously, pass ``return_reply=True`` as a parameter... ::

    from tfnz.location import Location

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    shell = container.spawn_process('/bin/bash')
    reply = shell.stdin("ps faxu\n".encode(), return_reply=True, drop_echo=True)
    print(reply.decode())

Launching a Shell
=================

While traditional to launch a bash process then attach the streams, on SmartOS we are able to connect to the 'real' shell. A few caveats are that trying to run synchronously basically doesn't work (for the initial log-on at least, data arrives in 'stutters'); that there is no parameter to run a remote process; and that a command is not executed until you send a 'return' ("\\n")::

    import time
    import sys
    from tfnz.location import Location

    def dc(obj, data):
        print(data.decode(), end='')
        sys.stdout.flush()

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    time.sleep(2)
    shell = container.spawn_shell(dc)
    shell.stdin(b'ps faxu')
    time.sleep(2)
    shell.stdin(b'\n')
    time.sleep(2)

Multi-container Applications
============================

We can ask a container for it's local (within cluster) IP, write pre-boot files and create start/reboot/terminate logic trivially within 20ft. However, by default each container is firewalled away from the other so we need to be able to open firewall holes. To achieve this you just call ``allow_connection_from`` on a container...::

    from tfnz.location import Location

    node = Location(debug_log=False).best_node()
    preboot = {'/usr/share/nginx/html/index.html': 'Hi!'}
    server_container = node.spawn('nginx', pre_boot_files=preboot)
    client_container = node.spawn('debian', sleep=True)
    test_cmd = "/native/usr/bin/wget --timeout=1 --tries=1 -q -O - http://" + \
                server_container.ip()

    reply = client_container.spawn_process(test_cmd).wait_until_complete()
    print("Before -->" + reply.decode())

    server_container.allow_connection_from(client_container)
    reply = client_container.spawn_process(test_cmd).wait_until_complete()
    print("After -->" + reply.decode())

``disallow_connection_from`` does what you'd expect it to.

Health checks and start/reboot/terminate logic are left for the user to determine. The contents of /native are undocumented.
