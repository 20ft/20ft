=========================
Building Container Images
=========================

20ft is designed to align as closely as possible with the modern toolset. Specifically this means using Docker's development tools and container images, and presenting containers as remote vms for IDEs or similar toolchains.

The Role of Docker
==================

Docker is used as an image builder, and gateway onto the wider world of docker images. 20ft itself only contains an image *cache*, the point being that it may need images to be uploaded before they can be run, and that it relies on the presence of a docker daemon - usually only on a development machine - to do so.


An Introduction to Dockerfile
=============================

A 'Dockerfile' is the container analog to 'Makefile'. The Makefile is concerned specifically with building the software and Dockerfile is concerned with solely building the image so they can (and usually do) coexist in the root directory of a project.

Docker builds disk images as a series of layers laid over each other. Imagine starting with a Debian base install, then adding a CMS, then adding fixtures ... and this is exactly what Docker does, except stopping at each step to snapshot the changes between the current filesystem and the filesystem at the end of the previous step. The great advantage of this is that common and/or time consuming steps only need to be performed once, with a cached result being used for future builds.

A Dockerfile is about as syntactically simple as it's possible to get. For example: ::

    FROM debian
    RUN apt update
    RUN apt install -y apache2
    COPY boot_script /
    CMD /bin/sh boot_script
    COPY index.html /var/www/html/

..  glossary::
    FROM
        Specifies the base layer to use, in this case Debian.

    RUN
        Is a command to run inside the container in order to create the next layer. So in this case the container is started up in the 'fresh Debian image' state and 'apt update' is run inside that image in order to create the next layer of files.

    COPY
        Copies a file from the host machine to the container image.

    CMD
        Tells the container engine which command to issue to actually run the container. (you may also see ENTRYPOINT)

The commands are executed by running ``docker build .`` from the root directory of the project; similarly running ``tfnz .`` implies that you want to run the most recent build. ::

    $ docker build .
    Sending build context to Docker daemon  4.096kB
    Step 1/7 : FROM debian
     ---> 8cedef9d7368
            .......................
    Step 7/7 : ADD index.html /var/www/html/
     ---> Using cache
     ---> 2f68a2591a20
    Successfully built 2f68a2591a20
    $ tfnz .
    0425101548.712 INFO     Connecting to: tiny.20ft.nz
    0425101548.717 INFO     Message queue connected
    0425101548.743 INFO     Handshake completed.
    0425101548.751 INFO     Ensuring layers are uploaded for: 2f68a2591a20
    0425101548.755 INFO     No layers need uploading for: 2f68a2591a20
    0425101548.756 INFO     Spawning container: b'zeftPyus7zWNpaxkhXPWZ5'
    0425101554.555 INFO     Container is running: b'zeftPyus7zWNpaxkhXPWZ5'

It is not the intention to create a full guide to Dockerfiles here, please see `Docker's reference <https://docs.docker.com/engine/reference/builder/>`_ for a full understanding.


Some Dockerfile Gotchas
=======================

Despite their simple syntax, there are some hidden complexities in Dockerfiles once you start to use them in earnest...

**Build contexts**

Docker creates an image by sending everything it thinks *might* be involved in the build to a separate daemon that does the actual building. This collection of information is called the build context and is everything in and below the current directory when ``docker build .`` is called. There are two problems with this:

* If you place large quantities of irrelevant content (crash dumps, disk images) in a subdirectory then these images are sent to the docker daemon every time you build. This *shouldn't* be a significant problem but will slow your builds considerably.

* More unfortunately, Docker will not follow symlinks - so if you have code that's shared between a number of projects and symlinked into the directory tree for the projects that use it, Docker will not be able to build them into a disk image.

**Put costliest first, most common last**

Since a change in the Dockerfile affects all the instructions below, it pays to make the instructions/content that change most frequently towards the bottom of the file. Similarly, costly (i.e. time consuming) operations are best placed at the top of the file to reduce the chances of a rebuild being forced by a subsequent change.

**State is not carried from one instruction to the next**

Each line is an independent instruction. So, for instance, this will not do what you would've hoped: ::

    RUN cd /root
    RUN echo "hello" > world

The first instruction creates a layer from the differences created by 'cd /root' (i.e. nothing); and the second creates a layer from the differences create by 'echo "hello" > world' - which will probably be written into /. Most Dockerfiles get around this with compound statements: ::

    RUN cd /root; \
        echo "hello" > world


**Don't forget to add -y**

A common pattern is... ::

    RUN apt-get update
    RUN apt-get upgrade

However, there is no interactive input so the second command will fail. The solution is that you need to add a (usually) '-y' flag to commands that are going to need confirming: ::

    RUN apt-get update
    RUN apt-get upgrade -y

**Use COPY not ADD**

Neither COPY nor ADD have the same semantics as the unix 'cp' command, particularly regarding directories, and many unpleasant surprises await. The most important result is that to recursively copy a directory tree you need ``COPY from/ to/`` and any globbing operators will cancel the recursion.

This is covered in more detail in `this excellent blog post <https://www.ctl.io/developers/blog/post/dockerfile-add-vs-copy/>`_.

**On removing files**

Often you will see a pattern such as::

    FROM alpine
    COPY build_files/ build_files/
    RUN build
    RUN rm -r build_files/

And the resulting container will not have removed the build files. This is (unfortunately) a naievety problem on my side - in that overlaying a filesystem with another that doesn't have the file doesn't produce no file. If this is a problem, build with ``docker build --squash`` which will take the resulting filesystem and flatten in into two layers - the base OS, and everything else. In many cases this has positive performance implications as well.

**When a build is not regarded as 'new'**

A build may not be regarded as "new" when a previous build will suffice. For instance, for Dockerfile... ::

    FROM debian
    RUN echo "hello" > world

Building the image gets... ::

    $ docker build .
    Sending build context to Docker daemon  2.048kB
    Step 1/2 : FROM debian
     ---> 8cedef9d7368
    Step 2/2 : RUN echo "hello" > world
     ---> Running in 16ba921bf022
     ---> 3960ae683e74
    Removing intermediate container 16ba921bf022
    Successfully built 3960ae683e74

We decide against the second step and comment it out ::

    $ docker build .
    Sending build context to Docker daemon  2.048kB
    Step 1/1 : FROM debian
     ---> 8cedef9d7368
    Successfully built 8cedef9d7368

Then decide that wasn't the problem after all and put it back in... ::

    $ docker build .
    Sending build context to Docker daemon  2.048kB
    Step 1/2 : FROM debian
     ---> 8cedef9d7368
    Step 2/2 : RUN echo "hello" > world
     ---> Using cache
     ---> 3960ae683e74
    Successfully built 3960ae683e74

Running 'tfnz .' we would hope that 20ft would run the most recent build, *but* 3960ae683e74 was actually built two builds ago and the most recent build is still 8cedef9d7368 so 'tfnz .' would run *that*. If you're getting "my change did nothing" frustrations this is the likely cause and the workaround is to merely state exactly which build you do want to run i.e 'tfnz 3960ae683e74'.

**Docker assumes an identical result every time**

Consider... ::

    FROM debian
    RUN date > timestamp
    COPY somefile /

The first time the Dockerfile is built the current date is written into the timestamp. We now change our dockerfile... ::

    FROM debian
    RUN date > timestamp
    COPY some_other_file /

And build again. However, because the first two instructions have not changed, and docker assumes an identical result every time, the contents of 'timestamp' will *not* be updated. This also has implications for versioning.

**Some nasty implications for security**

The 'identical result' observation has nasty security implications for the unwary. For instance, a typical Dockerfile might start with: ::

    FROM debian
    RUN apt update
    RUN apt install -y apache2

A few days later a security patch is released for apache2 and it would seem that rebuilding the Dockerfile would pull the latest (and presumably patched) binary off the Internet and use that instead. However, because none of the lines have actually changed, a daemon that has previously built this particular Dockerfile will assume it's cached results are still valid - leading to erroneously shipping the old (and insecure) binary. The only real solutions to this are to either clean-before-build or version packages as part of the Dockerfile itself.

**'docker clean'?**

You can see the layers stored in the Docker daemon with ``docker images``, but there is no 'docker clean'. Handy shortcuts are:

* ``docker images -q | xargs docker rmi -f $1`` removes all images. Because of dependency problems you may need to run it more than once.
* ``docker images | grep '<none>' | egrep -o '[0-9a-f]{12}' | xargs docker rmi -f $1`` removes all images that are not tagged.
* ``docker ps -qa | xargs docker rm $1`` stops and removes processes running in the local docker.

**Files not being removed when running rm instructions as part of the Dockerfile**

In essence what happens is that the loss of the file cannot be expressed using a filesystem layer. Investigations are continuing.

Some Thoughts about Versioning
==============================

One of the central concepts in modern software development is a tight control of versioning. Specifically that if I check out and build version '1234' at any time that I'll get a bit for bit identical result to the first time it was run. This turns out to be not quite true since the compiler may have changed, but fundamentally it works. The same is not quite true for versioning a Dockerfile.

Consider again our 'update; install' dockerfile above. The actual result from building the image depends on the current package versions so it is dependent on both time and what it is we are served by a third party so we cannot be said to have bit-level control over the build. One option is to state specifically which version of 'apache2' you are installing but this has three problems:

* You are now dependent on a third party to continue to host out of date packages.
* You no longer get security updates and
* The cascading requirements to explicitly manage versions becomes difficult to manage remarkably quickly.

If you are happy with not being able to *build* a bit-exact copy, taking a backup of the image and storing it as a single artifact is both safe and (because of UUID filenames) inherently versioned.

Backups
=======

Exporting an entire container image (consisting of all it's layers) is as simple as running ``docker save -o some_filename 3960ae683e74`` (obviously substituting the correct filename and image ID). The file format itself is just a tar archive of the individual layers plus some json metadata. Restoring a backup is merely ``docker import some_filename``.

Backing up entire images at once is, of course, inefficient. But this inefficiency is balanced out by the simplicity of a restore and knowing that if we should want to deploy an older version of a container, that this is very much an option.
