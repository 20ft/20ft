===========
Quick Start
===========

These installation instructions are broadly written for macOS - other unices are just a package manager away.

* Run the 20ft key installation script you will have been given
* Install the `Docker development kit <https://www.docker.com/products/docker#/mac>`_
* Install the `official Python 3 <https://www.python.org/downloads/>`_, `libnacl <https://nacl.cr.yp.to>`_ and `zmq <http://zeromq.org>`_ (using `homebrew <http://brew.sh>`_) ... ``brew install python3 libsodium zeromq``
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

You just launched your first container. Ctrl-C will end the process and clean up resources; and refreshing the browser will show that the container is no longer responding. Perfect.

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
