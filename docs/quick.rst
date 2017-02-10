===========
Quick Start
===========

At the time of writing, 20ft can be regarded as being very much beta (although the API should now be stable). As such, it is assumed you have already been sent a key pair. If you don't have one but would like to try the service, mail `davep@polymath.tech <mailto:davep@polymath.tech>`_ and one will be sent to you.

Installation
============

To ready a computer for being a 20ft client, choose one of the following...

**Using AWS**

* Create a `pre-installed instance <https://ap-southeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-b0a5a3d3>`_, ensuring the security group has ports 22 & 80 (inwards) open; then log in.
* You will need to make note of the instance's public IP which is available from the `Instances dashboard <https://ap-southeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#Instances:>`_, on the "Description" tab, under "IPv4 Public IP".
* Paste your key installation script.

**A Local VM**

* Import and run `this OVA appliance <https://s3-ap-southeast-2.amazonaws.com/tfnz/Ubuntu+20ft-preinstalled.ova>`_.
* Log in with ``ssh tfnz@tfnz``, password 'tfnz'.
* Paste your key installation script.

**On Bare Metal**

* Install `Ubuntu 16.04 LTS <https://www.ubuntu.com/download/server>`_.
* Paste ``curl https://20ft.nz/ubuntu-20ft-build-metal | /bin/bash``.
* Paste your key installation script.

**On macOS**

* Install `homebrew <http://brew.sh>`_
* Install the `Docker development kit <https://www.docker.com/products/docker#/mac>`_
* Install the `official Python 3 <https://www.python.org/downloads/>`_
* Paste ``curl https://20ft.nz/macos-20ft-build | /bin/bash``.
* Paste your key installation script.

Obviously skip any of the Install steps that have already been done on your machine (such as installing homebrew).

Your First Container
====================

Running nginx is the hello world of container orchestration. If the machine you're currently using has a 20ft key pair installed and is running a graphical desktop, you can launch your first container with ``tf -v --browser nginx``. This may take a little while, it...

* Connects to the default location provided by the key installation script, authenticates both` client and server and `sets up an encrypted tunnel <http://curvezmq.org/page:read-the-docs#toc5>`_.
* Ensures `nginx <https://hub.docker.com/_/nginx/>`_ is resident in your local docker image library and will pull it if not.
* Asks the location to choose a node for us then...
* Asks the node to spawn a container from the nginx image.
* Once the container is running the location will build a tunnel from a local port to port 80 on the container...
* Poll until it receives an HTTP 200 then...
* Opens a browser onto the local port so we can see the container running.

If logged into a remote server launch instead with ``sudo tf -v --public nginx`` and connect your browser to the public IP of the server.

Because we requested verbose logging (``-v``) you should see output something like::

    bash-3.2$ tf -v --browser nginx
    0209002658.728 INFO     Connecting to: tiny.20ft.nz
    0209002658.787 INFO     Ensuring layers are uploaded for: nginx
    0209002658.875 INFO     Fetching with 'docker pull' (may take some time): nginx
    0209002742.727 INFO     No layers need uploading for: nginx
    0209002742.738 INFO     Spawning container: wLxboFBbYj9uGW7AsYtv6k
    0209002743.916 INFO     Container is running: wLxboFBbYj9uGW7AsYtv6k
    0209002743.923 INFO     Created tunnel object: V45myZ4ANKAqRTv4aGBCCM (1932 -> 80)
    0209002745.146 INFO     Connected onto: http://localhost:1932/

You just launched your first container. Ctrl-C will end the process and clean up resources; and refreshing the browser will show that the container is no longer responding. Perfect.

A Sensible Question
===================

Why is the nginx image pulled locally when it is run in the cloud? The overall design of 20ft is assuming local development to remote deployment, hence needing to bring the image locally first. This will be changed in a future revision of the SDK.

Your First Docker Workflow
==========================

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
