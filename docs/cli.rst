===============================
Running Containers from the CLI
===============================

In the quickstart we used the command line to launch containers, map ports and start an interactive instance. Let's have a closer look at what 'tfnz' is capable of.

tfnz
====
 ::

    usage: tfnz [-h] [--location x.20ft.nz] [--local x.local] [-v] [-q] [-ti]
                [-e [VAR=value | VAR]] [-f src:dest]
                [-m [uuid:mountpoint | tag:mountpoint]] [-p 8080:80]
                [-w subdomain.my.com[:www.my.com[:certname]]] [--ssh 2222] [-s]
                [-z] [--systemd user@server.my.com]
                [--identity ~/.ssh/some_id.pem]
                source [command] ...

    positional arguments:
      source                if '.' runs the most recently added docker image; else
                            this is the tag or hex id of an image to run.
      command               run this command/entrypoint instead
      args                  arguments to pass to a script or subprocess

    optional arguments:
      -h, --help            show this help message and exit

    connection options:
      --location x.20ft.nz  use a non-default location
      --local x.local       a non-dns ip for the location

    launch options:
      -v, --verbose         verbose logging
      -q, --quiet           no logging
      -ti, --interactive    interactive, connect stdin and stdout
      -e [VAR=value | VAR], --env [VAR=value | VAR]
                            set an environment variable, possibly from current
      -f src:dest, --file src:dest
                            write a pre-boot file
      -m [uuid:mountpoint | tag:mountpoint], --mount [uuid:mountpoint | tag:mountpoint]
                            mount a volume
      -p 8080:80, --publish 8080:80
                            add a local->remote tcp proxy
      -w subdomain.my.com[:www.my.com[:certname]], --web subdomain.my.com[:www.my.com[:certname]]
                            publish on web endpoint

    development options:
      --ssh 2222            create an ssh/sftp wrapped shell on given port
      -s                    shorthand for --ssh 2222
      -z, --sleep           launch the container asleep (instead of entrypoint)

    server options:
      --systemd user@server.my.com
                            create a systemd service
      --identity ~/.ssh/some_id.pem
                            specify an identity file to use with --systemd

**A Subset Of These Options Are Compatible With 'docker run'**

* -e and --env are the same between both platforms
* -m and --mount, use the syntax from '-v' but refer to 20ft volumes and not local directories
* -p and --publish, still create container to local proxies, but only use the two part hostport:containerport syntax
* -ti, works the same but there is no -t or -i on its own
* trailing (optional) command and args are the same.

"location" can be passed to indicate that a location other than the default should be used (obviously you will need an account for this location). And "local" is to connect to a location by manually stating it's IP. This is most commonly used for better performance when the server is on the local lan.

"verbose" and "quiet" work in the familiar way. Regardless of the verbosity settings, errors will still be printed on the stderr stream (and the return code will be 1).

"web" publishes to a web endpoint on the load balancer - see :ref:`domains <domains>` in the CLI administration section for guidance on how to use these.

"ssh" creates an ssh server onto the container - see 'development' later.

"systemd" creates and starts a systemd unit on a server or vps to which the user has ssh access; and "identity" specifies the pem file to use to connect.

The env and mount options can be used multiple times.

**It is more performant to publish to a web endpoint than it is to create a proxy**

Note that tfnz (mostly) assumes you have a local docker instance running. The times when you don't need one are covered in :ref:`the images section <images>` in the administration chapter.

About Volumes
=============

You can only ever mount from the root of a volume. You cannot, for example, have a volume with subdirectories "mnt1" and "mnt2" and specify which subdirectory you want to mount within the container's filesystem.

Examples
========

``tfnz -w docs.sydney.20ft.nz tfnz/docs``

Publishes the image for this documentation onto an endpoint: docs.sydney.20ft.nz

``tfnz -ti alpine``

Runs an alpine linux container interactively.

``tfnz --sleep -s tfnz/docs``

Spawns a container from the documentation image but doesn't start it. It does, however, connect an ssh server from which we can mount the file system (sftp).

``tfnz -e EXAM=ple -p 8000:80 tfnz/env_test``

Spawns an environment testing container with 'EXAM=ple' set it its environment; and puts a tcp proxy between localhost:8000 and the webserver running on the container. `curl http://localhost:8000` returns the environment inside the container.

``tfnz -m example:/mnt -ti alpine``

Runs an alpine linux container interactively with the persistent volume tagged 'example' mounted on /mnt.

