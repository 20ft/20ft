===========
Quick Start
===========

The quick start assumes you have already received an invite email. If not, please email davep@20ft.nz to receive one.

Run on AWS
==========

Use the `ready made AMI <https://ap-southeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#LaunchInstanceWizard:ami=ami-5435f336>`_ (runs fine on t2.nano, login with alpine@) and create an account using the command sent with your invite email.

To Install on my Local Machine
==============================

To ready a computer for being a 20ft development client, `install Docker <https://store.docker.com/search?type=edition&offering=community>`_ then choose which platform to install on - Docker or Python 3. Installing on Docker is simplest but (especially on mac) may prove to have worse performance; Installing into Python 3 needs a Python 3 environment on the development machine, *and also a local docker instance* but should prove to be faster. You will also need gcc and make, if they're not installed already. Note that for any advanced development you will be needing a Python 3 environment anyway.

**For Docker** Install with ``curl -s https://20ft.nz/docker | sh``.

**For Python 3** Ensure you have pip installed then run ``pip3 install tfnz``.

Man pages and tab completion can be installed for either platform with ``curl -s https://20ft.nz/shell | sh``. I'd recommended pulling the 'nginx', 'postgres:alpine' and 'alpine' docker images too.


Your First Container
====================

Running nginx is the hello world of containers. Launch your first container with ``tfnz -p 8080:80 nginx``. This will...

* Connect to the default location (in this case "tiny.20ft.nz") and set up an encrypted tunnel.
* Receive a list of resources we can use.
* Ensure all the layers for the nginx image have been uploaded.
* Spawn a container from the nginx image.
* Once the container is running a proxy will be started from port 8080 locally to port 80 on the container.

You should see output something like::

    0409112637.525 INFO     Connecting to: tiny.20ft.nz:2020
    0409112637.531 INFO     Message queue connected
    0409112637.600 INFO     Handshake completed.
    0409112637.602 INFO     Ensuring layers (3) are uploaded for: nginx
    0409112637.632 INFO     Spawning container: b'xfqMKCwqai9KTURtc7GRUi'
    0409112639.978 INFO     Container is running: b'xfqMKCwqai9KTURtc7GRUi'
    0409112640.017 INFO     Created tunnel object: b'iJ6pyAg2FBRjyo5VPSj6Bg' (8080 -> 80)

Open a web browser onto `http://localhost:8080 <http://localhost:8080>`_ and you should see the "Welcome to nginx!" page (those using the AMI will need to open another session and ``curl http://localhost:8080``. You just launched your first container :) Ctrl-C will end the process and clean up resources; and refreshing the browser will show that the container is no longer responding. Perfect.


Your First Docker Workflow
==========================

It's all for nothing if we can't change the code that's running, so let's customise our nginx container by replacing the index.html. First, make a new index file::

    davermbp:tmp dpreece$ cat > index.html << EOF
    > Hello World!
    > EOF

And a dockerfile to build our new image::

    davermbp:tmp dpreece$ cat > Dockerfile << EOF
    > FROM nginx
    > ADD index.html /usr/share/nginx/html/
    > EOF

Get Docker to build the image::

    davermbp:tmp dpreece$ docker build .
    Sending build context to Docker daemon  3.072kB
    Step 1/2 : FROM nginx
     ---> 5e69fe4b3c31
    Step 2/2 : ADD index.html /usr/share/nginx/html/
     ---> c76560c98518
    Removing intermediate container 3363972fc7e0
    Successfully built c76560c98518

Now we can instruct 20ft to use this image with ``tfnz -p 8080:80 .`` - note the '.' that lets 20ft know we want the latest build.::

    davermbp:tmp dpreece$ tfnz -p 8080:80 .
    0409113224.440 INFO     Connecting to: tiny.20ft.nz:2020
    0409113224.454 INFO     Message queue connected
    0409113224.529 INFO     Handshake completed.
    0409113224.531 INFO     Ensuring layers (4) are uploaded for: c76560c98518
    0409113224.602 INFO     Getting docker to export layers...
    0409113232.047 INFO     Uploading: fd2924e4e9740a4a
    0409113232.047 INFO     Uploading slabs: 1
    0409113232.058 INFO     Location received slab: 0
    0409113232.068 INFO     Location received complete layer: fd2924e4e9740a4a
    0409113232.810 INFO     Spawning container: b'WvpQ9LdQqTeSrzUyjkA7ce'
    0409113235.721 INFO     Container is running: b'WvpQ9LdQqTeSrzUyjkA7ce'
    0409113235.787 INFO     Created tunnel object: b'Q8XqBbLsMrApmnDrRj5MFN' (8080 -> 80)

...opening the browser again gives "Hello World!". Easy :)

Note that both ``tfnz --help`` and ``man tfnz`` do what you would hope.

A Shell
=======

Many images have a shell as their application. Using the ``-ti`` flag we can connect stdin and stdout and open a shell in a new container quickly...::

    davermbp:tmp dpreece$ tfnz -ti alpine
    1114191344.444 INFO     Connecting to: tiny.20ft.nz:2020
    1114191344.461 INFO     Message queue connected
    1114191344.483 INFO     Handshake completed
    1114191344.591 INFO     Ensuring layers (1) are uploaded for: alpine
    1114191344.592 INFO     Spawning container: b'GyYjWRVKjYpUk6HEAB5VoP'
    1114191345.271 INFO     Container is running: b'GyYjWRVKjYpUk6HEAB5VoP'
    Interactive session - escape is triple '^]'.
    / # ps
    PID   USER     TIME   COMMAND
        1 root       0:00 /bin/sh
        3 root       0:00 ps
    / # exit
    1114191353.335 INFO     Disconnecting
    1114191353.335 INFO     Container has exited and/or been destroyed: b'GyYjWRVKjYpUk6HEAB5VoP'

The treatment of the tty in this mode is a little simplistic, and a better result can be had by running with ``-s`` flag and then ssh'ing into the container with ``ssh -p 2222 root@localhost``.
