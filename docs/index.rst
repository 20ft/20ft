===============
The 20ft.nz SDK
===============

.. topic:: Overview

   20ft.nz is a (currently) invite only container hosting service. It is unique in that it does not require an orchestrator and instead provides a CLI and Python SDK to be able to interact with the service directly. It has a strong focus on security, is explicit about where code runs, and uses Docker's images and development tools.

   For more information email davep@polymath.tech.


Introduction
============

Conventional container platforms require that you interact with an orchestrator - Kubertenes, Marathon, Nomad etc. They all attempt to build a statically described platform and with little or no support for ordering, custom test scripts or location awareness.

20ft is a dynamic platform with an Object Oriented SDK - you write orchestration instructions in the same way you write other software. It's simpler, makes no assumptions about what you are trying to achieve and retains compatibility with Docker containers. The platform garbage collects on disconnection so don't worry about leaking containers, tunnels, addresses or otherwise - it's all taken care of.


Architecture
============

There are four main actors in a 20ft session: The client, the location, the nodes and their containers.

Client
   A piece of software running the 20ft sdk. This client can be daemonised (run as a service) and can therefore act as a server ... but from 20ft's point of view is still a client of the service. Clients need to connect outwards to the Internet on TCP port 5555 and must be able to resolve DNS TXT records.

Location
   Effectively the "server" of a client server pair, the location acts as a secured message broker, an image server, a resource manager, and can create TCP tunnels onto individual containers. It needs TCP port 5555 to be open.

Node
   The nodes can spawn containers and will update the Location with it's current cpu and memory statistics.

Container
   Once spawned, a container is provided with a non-routable ip and default gateway. Containers objects in the SDK can also fetch a file from the container, place files into the container, spawn a process in the container and fetch container logs.



===========
Quick Start
===========

These installation instructions are broadly written for macOS - other unices are just a package manager away.

* Run the 20ft key installation script you will have been given
* Install the `Docker development kit <https://www.docker.com/products/docker#/mac>`_
* Install Python 3, `libnacl <https://nacl.cr.yp.to>`_ and `zmq <http://zeromq.org>`_ (using `homebrew <http://brew.sh>`_) ... ``brew install python3 libsodium zeromq``
* Install the 20ft sdk ... ``pip3 install tfnz``

My First Container
==================

Running nginx is the hello world of container orchestration. Launch your first container with ``tf -v --browser nginx``. This may take a little while, it...

* Connects to the default location provided by the key installation script, authenticates both` client and server and `sets up an encrypted tunnel <http://curvezmq.org/page:read-the-docs#toc5>`_.
* Ensures `nginx <https://hub.docker.com/_/nginx/>`_ is resident in your local docker image library and will pull it if not.
* Asks the location to choose a node for us then...
* Asks the node to spawn a container from the nginx image.
* Once the container is running the location will build a tunnel from a local port to port 80 on the container...
* Poll until it receives an HTTP 200 then...
* Opens a browser onto the local port so we can see the container running.

Because we requested verbose logging (``-v``) you should see output something like::

    bash-3.2$ tf -v --browser nginx
    1231204009.014 INFO     Connecting to: tiny.20ft.nz
    1231204009.069 INFO     Ensuring layers are uploaded for: nginx
    1231204009.227 INFO     No layers need uploading for: nginx
    1231204009.325 INFO     Spawning container: Crx6x786fTrZpo66CtHE7L
    1231204010.141 INFO     Container is running: Crx6x786fTrZpo66CtHE7L
    1231204010.142 INFO     Created tunnel object onto: Crx6x786fTrZpo66CtHE7L (7805 -> 80)
    1231204012.293 INFO     Connected onto: http://localhost:7805/

There, you just launched your first container. Ctrl-C will end the process and clean up resources; and refreshing the browser will show that the container is no longer responding. Perfect.

My First Docker Workflow
========================

It's all for nothing if we can't change the code that's running, so let's customise our nginx container by replacing the index.html. First, make a new index file::

   bash-3.2$ cat > index.html << EOF
   > Hello World!
   > EOF

And a dockerfile to build our new image::

   bash-3.2$ cat > Dockerfile << EOF
   > FROM nginx
   > ADD index.html /usr/share/nginx/html/
   > EOF

Get Docker to build the image::

   bash-3.2$ docker build .
   Sending build context to Docker daemon   894 kB
   Step 1 : FROM nginx
    ---> 05a60462f8ba
   Step 2 : ADD index.html /usr/share/nginx/html/
    ---> 91e2255020fe
   Removing intermediate container 2ef8581c6ad4
   Successfully built 91e2255020fe

Now we can instruct 20ft to use this image with ``tf -v --browser .`` - note the '.' that lets 20ft know we want the latest build.::

    bash-3.2$ tf -v --browser .
    0109174501.466 INFO     Connecting to: tiny.20ft.nz
    0109174501.629 INFO     Ensuring layers are uploaded for: 91e2255020fe
    0109174501.692 INFO     Getting docker to export layers (this can take a while)...
    0109174510.963 INFO     Background uploading: 145ef...fc6d6/layer.tar
    0109174512.292 INFO     Spawning container: x2LuQnkN4t8vLY5iWTvP6G
    0109174512.313 INFO     The node is downloading layers
    0109174513.867 INFO     Container is running: x2LuQnkN4t8vLY5iWTvP6G
    0109174513.896 INFO     Created tunnel object onto: u3H8iBpKen3w8kuCzEuTDL (6624 -> 80)
    0109174515.906 INFO     Connected onto: http://127.0.0.1:6624/

...and a browser opens with "Hello World!". Easy :)

Note that both ``tf --help`` and ``man tf`` do what you would hope.

Production
==========

Currently 20ft is designed as a compute resource and hence has no explicit support for public Internet connectivity. The best way to create a server for 20ft is to:

* Create a VM on a public Internet provider (or an intranet). The VM will require little compute power so a small instance will work well.
* Use monit or similar process manager to...
* Run ``tf -v --bind aa.bb.cc.dd --offset n image`` to run the container and create tunnels onto its exposed ports.

The offset is optional and maps (for example) container port 80 to local port 8080 (with an offset of 8000). This is purely so tf does not need to be run as root. This technique works equally well for Intranets or the public Internet. For the public Internet is recommended that web servers ve run behind a proxy or source protecting CDN such as `Cloudflare <https://cloudflare.com/>`_ or `Fastly <https://fastly.com/>`_ (both of which provide low volume accounts free of charge).

The ability to directly bind exposed ports onto an Internet addressable IP will be available soon.


====================
20ft.nz Python 3 SDK
====================

The vast majority of power in 20ft is contained in the Python SDK. The SDK is BSD licensed so feel free to modify, extend and distribute either the SDK or applications based on it (including commercial applications) without either fee or attribution. The ``tf`` command is also covered by the license.

It is designed to enable the simple construction of orchestration applications including (but not limited to): unit testing; deployment and scaling; and unique container native architectures.

All the examples below are complete programs. They can be run by pasting the example into a text file (called, say, 'scratch.py') then running with ``python3 scratch.py``.

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

The Location object by default connects to the location in '~/.20ft/default_location', and this behaviour can be changed by merely passing the fqdn of an alternative on which you have an account - for instance Location('chch.20ft.nz'). You may create multiple Location objects but only one per location. debug_log is one of three values: None (the default) does nothing to the `user configured <https://docs.python.org/3/howto/logging.html#logging-basic-tutorial>`_  logging; False sets up Python debugging to the 'info' level (-v on tf); and True sets Python debugging to the 'debug' level (-vv on tf).

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


=================
Advanced Spawning
=================

Pre-boot files
==============

In reality it's rare that a single configuration, baked into the container image during ``docker build``, is going to be suitable for all situations. A database server will need different user configuration; a load balancer needs to be told *what* to load balance; a container under test needs to be passed fixtures and so on. The 'traditional' Docker way of doing this is to write a script that gets started in lieu of the desired process start, is passed various parameters in environment variables and is expected to render any configuration changes within the container itself before starting the desired process. They're nasty to write; worse to debug; and quickly become informal (ie undocumented) interfaces onto the underlying functionality.

Thankfully there's a better way to effect a dynamic configuration and that's by using pre-boot files. These are just text files that are passed as part of the ``spawn`` call and are written into the container immediately prior to boot. They are nothing more than renders of the application's configuration files - and as such can be created with anything that will render a template. Here is a simple implementation...::

    import signal
    from tfnz.location import Location

    location = Location(debug_log=True)
    preboot = {'/usr/share/nginx/html/index.html': 'Hello World!'}
    container = location.best_node().spawn('nginx', pre_boot_files=preboot)
    container.attach_browser()
    signal.pause()

Obviously you are free to debug these renders client side, and in Python (instead of bash). Preboot files also make an excellent basis for higher level components i.e. a single 'LoadBalancer' class that uses pre-boot files as it's implementation.

Launching Processes in Containers (aka Pods)
============================================

"Container style" launch-at-boot of a single server process obviously doesn't cover all use cases so in 20ft it's possible to launch a process inside a pre-booted container. There can be multiple processes running concurrently and they can be run either synchronously to completion, or asynchronously with callbacks for the stdout stream and process termination. Some examples: Synchronously... ::

    from tfnz.location import Location

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    container.wait_http_200()
    data = container.spawn_process('ps faxu').wait_until_complete()
    print(str(data, 'ascii'))

Asynchronously... ::

    import time
    from tfnz.location import Location

    def dc(obj, data):
        print(str(data, 'ascii'), end='')

    def tc(obj):
        print("Vmstat terminated")

    def sleep_tc(obj):
        print("---Sleep terminated---")

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx')
    vmstat = container.spawn_process('vmstat 1', data_callback=dc, termination_callback=tc)
    sleep = container.spawn_process('sleep 3', termination_callback=sleep_tc)
    time.sleep(10)
    vmstat.destroy()  # just so we get the termination callback - would still garbage collect without it

The concept of multiple processes in a single container can be implemented by starting the container 'asleep' then launching processes as and when you see fit. This is illustrated below... ::

    import signal
    from tfnz.location import Location

    location = Location(debug_log=False)
    container = location.best_node().spawn('nginx', sleep=True)
    print(str(container.spawn_process('ps').wait_until_complete(), 'ascii'))
    process = container.spawn_process('nginx')
    container.wait_http_200()
    print(str(container.spawn_process('ps').wait_until_complete(), 'ascii'))
    signal.pause()

Concurrent Booting
==================

20ft containers are started asynchronously - that is to say that the actions of asking a container to start and the container having started are, from the perspective of the user, completely decoupled. As with all things this is obvious given an example:

The image used in these examples is a fairly heavy Apache/Mezzanine/Django/Postgres stack with non-trivial startup costs. Consider the synchronous case::

    import logging
    from tfnz.location import Location

    location = Location('tiny.20ft.nz', debug_log=False)
    location.ensure_image_uploaded('337c501c333c')
    logging.info("-----Starting")
    for n in range(0, 10):
        container = location.best_node().spawn('337c501c333c', no_image_check=True)
        container.wait_http_200(fqdn="www.atomicdroplet.com")
    logging.info("-----Finished")

Results in::

    1207165016.497 INFO     Connecting to: tiny.20ft.nz
    1207165016.609 INFO     Location has sent resource offer
    1207165016.610 INFO     Ensuring layers are uploaded for: 337c501c333c
    1207165016.684 INFO     No layers need uploading for: 337c501c333c
    1207165016.684 INFO     -----Starting
    1207165016.763 INFO     Spawning container: jcSGEaxhkKxQwwHomowbdb
    1207165016.763 INFO     Waiting on http 200: jcSGEaxhkKxQwwHomowbdb
    .....snip
    1207165125.548 INFO     Container is running: uvUiGjDMZJ3yanGFoCHJVb
    1207165125.549 INFO     Created tunnel object onto: uvUiGjDMZJ3yanGFoCHJVb (3365 -> 80)
    1207165132.579 INFO     Connected onto: http://www.atomicdroplet.com:3365/
    1207165132.579 INFO     -----Finished

76.9 seconds. In parallel::

    import logging
    from tfnz.location import Location

    location = Location('tiny.20ft.nz', debug_log=False)
    location.ensure_image_uploaded('337c501c333c')
    containers = []
    logging.info("-----Starting")
    for n in range(0, 10):
        container = location.best_node().spawn('337c501c333c', no_image_check=True)
        containers.append(container)
    for container in containers:
        container.wait_http_200(fqdn="www.atomicdroplet.com")
    logging.info("-----Finished")

Gives::

    1207165538.478 INFO     Connecting to: tiny.20ft.nz
    1207165538.584 INFO     Location has sent resource offer
    1207165538.584 INFO     Ensuring layers are uploaded for: 337c501c333c
    1207165538.736 INFO     No layers need uploading for: 337c501c333c
    1207165538.736 INFO     -----Starting
    1207165538.787 INFO     Spawning container: z8JprcSwZd5wt8k8jSKqFE
    1207165538.837 INFO     Spawning container: aSXB2RpMcA2sihyRzvf2cj
    1207165538.900 INFO     Spawning container: EqSNk64z2WBUiWpjMCKtA7
    ....
    1207165541.372 INFO     Container is running: fs5SCYGpqE6prAtfGwj6w3
    1207165541.900 INFO     Container is running: diosgkCANemzCV4GcPjsz4
    1207165542.148 INFO     Container is running: UyxWTxCx6jRBdHJwbMA2q8
    1207165542.736 INFO     Container is running: VAkyf9jZNZv7Fk6nrphGci
    ....
    1207165555.126 INFO     Connected onto: http://www.atomicdroplet.com:6052/
    1207165555.126 INFO     Waiting on http 200: GUQxBDh9WyCpmBt3xktit2
    1207165555.132 INFO     Created tunnel object onto: GUQxBDh9WyCpmBt3xktit2 (1448 -> 80)
    1207165556.523 INFO     Connected onto: http://www.atomicdroplet.com:1448/
    1207165556.523 INFO     Waiting on http 200: VAkyf9jZNZv7Fk6nrphGci
    1207165556.528 INFO     Created tunnel object onto: VAkyf9jZNZv7Fk6nrphGci (1452 -> 80)
    1207165557.990 INFO     Connected onto: http://www.atomicdroplet.com:1452/
    1207165557.990 INFO     -----Finished

19.25 seconds - one quarter the time. This is also the first time we split spawn into separate ``ensure_image_uploaded`` and ``spawn`` calls since ensuring the upload only needs to happen once.

Obviously this is a somewhat contrived example but the lesson is simple: If you can start containers ahead of when you need them, you will enjoy a (very) significant performance boost.


=========================
Unit Testing with PyCharm
=========================

PyCharm offers built in support for unit testing. Writing unit tests for containers on 20ft is no different from any other 20ft script. However, it's worth pointing out that the test case class can initialise itself just once, then use the resources in the remainder of the script. For example... ::

   import requests
   from unittest import TestCase, main
   from tfnz.location import Location


   class TfTest(TestCase):

       @classmethod
       def setUpClass(cls):
           cls.location = Location(debug_log=False)
           cls.location.ensure_image_uploaded('nginx')

       def test_spawn_preboot(self):
           # write configuration files before we boot
           preboot = {'/usr/share/nginx/html/index.html': 'Hello World!'}
           container = TfTest.location.best_node().spawn('nginx', pre_boot_files=preboot, no_image_check=True)
           self.assertTrue(b'Hello World!' in container.fetch('/usr/share/nginx/html/index.html'))

       def test_tunnels_http(self):
           container = TfTest.location.best_node().spawn('nginx', no_image_check=True)

           # creating a tunnel after http 200
           tnl = container.wait_http_200()
           r = requests.get('http://127.0.0.1:' + str(tnl.localport))
           self.assertTrue('<title>Welcome to nginx!</title>' in r.text, 'Did not get the expected reply')

   if __name__ == '__main__':
       main()

So the Location object is created only once, and we the image is 'ensured' instead of being tested on every spawn.

To run this:

* Create a pure Python project in PyCharm.
* Add the script above (not that you will need the requests package installed)
* Select "Edit Configurations" from the toolbar
* Click the '+' button to create a new configuration - select "Python tests -> Unittests"
* Enter the name of your script into the "Script" box, leave everything else alone.
* Click OK

You should now have a green 'Run' button next to the configuration, clicking it should create something like this:

.. image:: _static/unit_test.png

==============
Known Problems
==============

Unfortunately there are still some small incompatibilities between container infrastructures. Neither of these two fixes is unique to 20ft...

**Apache 2** needs ``AcceptFilter http none`` somewhere in it's configuration.

**PostgreSQL** needs ``dynamic_shared_memory_type = none`` in postgresql.conf.

=========
Reference
=========


.. autoclass:: tfnz.location.Location
    :members:

.. autoclass:: tfnz.node.Node
    :members:

.. autoclass:: tfnz.container.Container
    :members:

.. autoclass:: tfnz.tunnel.Tunnel
    :members:

.. autoclass:: tfnz.process.Process
    :members:
