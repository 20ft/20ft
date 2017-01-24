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

The Location object by default connects to the location in '~/.20ft/default_location', and this behaviour can be changed by merely passing the fqdn of an alternative on which you have an account - for instance Location('syd.20ft.nz'). You may create multiple Location objects but only one per location. debug_log is one of three values: None (the default) does nothing to the `user configured <https://docs.python.org/3/howto/logging.html#logging-basic-tutorial>`_  logging; False sets up Python debugging to the 'info' level (-v on tf); and True sets Python debugging to the 'debug' level (-vv on tf).

We have a 'last_image' function as part of the tfnz.location module. So the Docker workflow example is::

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

Some Logs
=========

20ft is able to retrieve the container logs which arrive as a list of dictionaries.

Modify our script again::

    import signal
    import json
    from tfnz.location import Location, last_image

    location = Location(debug_log=False)
    container = location.best_node().spawn(last_image())
    container.attach_browser()
    for log in container.logs():
        print(json.dumps(log, indent=4))
    signal.pause()

Putting and Fetching files
==========================

It's important to note that a 20ft "fetch" or "put" relates to a single file and not an archive of an entire filesystem branch (you may have seen this in Docker). While convenient, the file will be loaded into memory so this is not a great way to send large files. They are blocking calls and may throw ValueError. Try... ::

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

TCP (only) tunnels can be created from localhost onto a container. The local port number can be either set or left blank (in which case it is chosen for you and becomes the ``.localport`` property of the tunnel)... ::

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

