=============
Using the CLI
=============

In the quickstart we used the command line to launch containers, map ports and start a vm. Let's have a closer look at what 'tf' is capable of, starting with the help message: ::

    usage: tf [-h] [--location x.20ft.nz] [--local x.local] [-v] [-q]
              [-e VAR=value] [-f src:dest] [-m uuid:mountpoint] [-p 8080:80]
              [-c script.sh] [-a tag] [-w test-b.20ft.nz] [-X tag] [--ssh 2222]
              [-s] [-z] [-d]
              source ...

    positional arguments:
      source                if 'XXX.py' exists and implements tf_main, call the
                            method; if '.', runs the most recently added docker
                            image; else this is the id of an image to run
      args                  arguments to pass to a script or subprocess (you may
                            need "--", see man page)

    optional arguments:
      -h, --help            show this help message and exit

    connection options:
      --location x.20ft.nz  use a non-default location
      --local x.local       a non-dns ip for the location

    launch options:
      -v                    verbose logging
      -q                    no logging
      -e VAR=value          set an environment variable
      -f src:dest           write a pre-boot file
      -m uuid:mountpoint    mount a volume
      -p 8080:80            add a local:remote tcp proxy
      -c script.sh          use this command (in container) to start
      -a tag                advertise (across account) container for connectivity
      -w test-b.20ft.nz     publish on web endpoint

    local/interactive options:
      --ssh 2222            create an ssh/sftp wrapped shell on given port
      -s                    short form for "--ssh 2222"
      -z                    launch the container asleep (instead of cmd)
      -d                    ssh explicit commands run without a pty and
                            synchronously

"Verbose" and "Quiet" work in the familiar way. Regardless of the verbosity settings, a validation error that causes the failure of 'tf' will still be printed on the stderr stream (and the return code will be 1).

"Location" can be passed to indicate that a location other that the one in ~/.20ft/default_location should be used - obviously you will need a key pair for your account on this location. And "Local" is to connect to a location by manually stating it's IP. This is most commonly used for better performance when the server is on the local lan.

Running Containers
==================

Running a container is as simple as typing ``tf nginx`` (for example). Under the hood this finds a node, instantiates the container and runs it from the combination of the 'entrypoint' and 'command' items in their metadata. The source is either a tagged image name ('nginx' or 'rantydave/env_test') or short form id ('a8b0ff411d12'). The latter should be used where version control is important.

Relevant options for running containers are:

* A portmap which is the specification for a TCP proxy running between localhost:local-port and remote-ip:remote-port on the container. Note that on the container accesses will appear to come from a gateway and not over localhost.
* Environment variables of the traditional form ENVIRONMENT=value that will be added to any environment variables stated in the container's metadata or boot scripts.
* A local file that will be copied to a given location in the container before boot.
* A volume that will be mounted in the container at the given mountpoint.

Each of these options can be added as many times as necessary. For example: ::

    dpreece@davermbp ~> tf -p 8080:8080 -e NAME=fred -e COFFEE=flat-white rantydave/env_test
    0424135901.799 INFO     Connecting to: tiny.20ft.nz
    0424135901.814 INFO     Message queue connected
    0424135901.874 INFO     Handshake completed.
    0424135901.898 INFO     Ensuring layers (2) are uploaded for: rantydave/env_test
    0424135901.914 INFO     Spawning container: b'TFJuDM3aP4vu3iSqhEpVbP'
    0424135903.714 INFO     Container is running: b'TFJuDM3aP4vu3iSqhEpVbP'
    0424135903.715 INFO     Created tunnel object: b'En2u6LsH7gcDNaFZ5XohLK' (8080 -> 8080)

Then in a separate terminal: ::

    dpreece@davermbp ~> curl http://localhost:8080
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    HOSTNAME=ctr-TFJuDM3aP4vu3iSqhEpVbP
    COFFEE=flat-white
    HOME=/root
    TERM=xterm
    PWD=/
    NAME=fred
    SHLVL=1

Showing that the portmap worked and the two environment variables were passed.

To destroy the container, quit the 'tf' instance with Ctrl-C (or a signal).

SSH/SFTP
========

It is possible to add an ssh/sftp server onto your container with '--ssh' then the port number for it to listen on (it binds to the localhost address). The ssh facility is primarily for debugging a running container.

For instance, spawn a container... ::

    dpreece@davermbp ~> tf --ssh 2222 alpine
    0424134022.422 INFO     Connecting to: tiny.20ft.nz
    0424134022.441 INFO     Message queue connected
    0424134022.500 INFO     Handshake completed.
    0424134022.520 INFO     Ensuring layers (1) are uploaded for: alpine
    0424134022.537 INFO     Spawning container: b'no95z24rdN5iZpEQmbExt2'
    0424134024.424 INFO     Container is running: b'no95z24rdN5iZpEQmbExt2'
    0424134024.427 INFO     SSH server listening on port: 2222

And now connect from another terminal. Additional authentication is bypassed so any username/password will work. ::

    dpreece@davermbp ~> ssh -p 2222 root@localhost
    Welcome to Alpine!

    The Alpine Wiki contains a large amount of how-to guides and general
    information about administrating Alpine systems.
    See <http://wiki.alpinelinux.org>.

    You can setup the system with the command: setup-alpine

    You may change this message by editing /etc/motd.

    ctr-no95z24rdN5iZpEQmbExt2:~#

Sftp works the same way: ::

    dpreece@davermbp ~> sftp -P 2222 root@localhost
    Connected to localhost.
    sftp> ls
    bin     dev     etc     home    lib     media   mnt     native  proc    root    run     sbin    srv     sys     system  tmp     usr     var

Note that '-s' can be used instead of '--ssh 2222'.

Remote processes can be launched directly from the command line. 20ft will attempt to find a shell to run the command (currently bash or ash) and if it fails will attempt to 'directly inject' the command into the container. In the usual case (where it does find a shell), see that 'composite' instructions can be given to the shell: ::

    dpreece@davermbp ~> ssh -p 2222 root@localhost "uname"
    Linux
    dpreece@davermbp ~> ssh -p 2222 root@localhost "ping yahoo.com"
    PING yahoo.com (98.139.183.24): 56 data bytes
    64 bytes from 98.139.183.24: seq=0 ttl=52 time=231.634 ms
    64 bytes from 98.139.183.24: seq=1 ttl=52 time=230.580 ms
    64 bytes from 98.139.183.24: seq=2 ttl=52 time=229.590 ms
    64 bytes from 98.139.183.24: seq=3 ttl=52 time=232.669 ms
    ^CKilled by signal 2.
    dpreece@davermbp ~> ssh -p 2222 root@localhost "cd /usr ; ls -Fl"
    total 19
    drwxr-xr-x    2 root     root           139 Mar  3 11:20 bin/
    drwxr-xr-x    2 root     root             6 Mar  3 11:20 lib/
    drwxr-xr-x    5 root     root             5 Mar  3 11:20 local/
    drwxr-xr-x    2 root     root            38 Mar  3 11:20 sbin/
    drwxr-xr-x    4 root     root             4 Mar  3 11:20 share/

A couple of caveats with ssh/sftp:

* Neither of these are intended as production servers and only exist as an aid to development and administration.
* The sftp server does not support changing attributes (owner, chmod etc).

Volumes
=======

Containers that destroy with the session are of limited usefulness without a way of persistently storing data. In 20ft this is done by mapping in an entire filesystem rather than by providing block level access and making the container format, mount etc. The major advantages to this are that it's simpler, access is *fast*, and that containers store their persistent data on the zfs filesystem. The downside is that code and the data it accesses need to be run on the same node.

Volumes are managed with the 'tfvoladm' command: ::

    dpreece@davermbp ~> tfvoladm
    usage: tfvoladm [-h] [--location x.20ft.nz] [--local x.local]
                    {list,create,destroy} ...

    optional arguments:
      -h, --help            show this help message and exit
      --location x.20ft.nz  use a non-default location
      --local x.local       a non-dns ip for the location

    commands:
      {list,create,destroy}
        list                list available volumes and nodes
        create              create a volume
        destroy             destroy a volume

The 'location' and 'local' flags work the same as for 'tf'. The three commands are what you might expect. Let's create a volume: ::

    dpreece@davermbp ~> tfvoladm create
    {
      "node": "pVy+I8zLW8GVNh8NbESsF8626ARc2i3yUu0DvIdBsXQ=",
      "volume": "Rg6cGAQqHVBCB2DwYrggoV"
    }

See that it returns a json object describing the node the volume is resident on and a uuid for the volume itself. tfvoladm automatically chooses the node with the most storage.

A list of all (our) volumes is similarly compatible with json: ::

    dpreece@davermbp ~> tfvoladm list
    {
      "pVy+I8zLW8GVNh8NbESsF8626ARc2i3yUu0DvIdBsXQ=": [
        "Rg6cGAQqHVBCB2DwYrggoV"
      ],
      "zSp2CcFVUfNQB3h82dCXw4CP0gmEBnEzG9B2MjaeZFs=": [],
      "z5DBGbW0JLuDlSNAKw0gLJquMajBzKzgH0FW9HsEgnk=": []
    }

Here we have a dictionary of the three nodes we can access, and the volumes we can access on those nodes. We can see volume 'Rg6c..." on the "pVy+..." node and no others.

Finally: ::

    dpreece@davermbp ~> tfvoladm destroy Rg6cGAQqHVBCB2DwYrggoV
    dpreece@davermbp ~> tfvoladm list
    {
      "pVy+I8zLW8GVNh8NbESsF8626ARc2i3yUu0DvIdBsXQ=": [],
      "z5DBGbW0JLuDlSNAKw0gLJquMajBzKzgH0FW9HsEgnk=": [],
      "zSp2CcFVUfNQB3h82dCXw4CP0gmEBnEzG9B2MjaeZFs=": []
    }

The "destroy" command is silent but listing our available volumes show that it is no longer there. Note that destroy for a non-existent filesystem is also silent (the thinking being that the outcome is the same), but exits with code 1.

There are currently no quota or other options, but you can create a filesystem with 'tfvoladm create --sync' for a filesystem that guarantees that writes will be physically on disk when a sync returns. Note that there is a significant performance penalty for this.

Mounting Volumes
================

There are two possibilities when it comes to mounting a volume the first time: either it is mounted somewhere there is data already, or on a new (or empty) directory/inode. In the former case the volume 'absorbs' the content the first time it is instantiated, and in the latter case a tree of directories will be constructed to ensure the empty inode exists before the mount happens. Let's see it in practice... ::

    dpreece@davermbp ~> tfvoladm create
    {
      "node": "pVy+I8zLW8GVNh8NbESsF8626ARc2i3yUu0DvIdBsXQ=",
      "volume": "Vz9jfz2pbBqQTW8GsVQ2B8"
    }
    dpreece@davermbp ~> tf -p 8080:80 -m Vz9jfz2pbBqQTW8GsVQ2B8:/usr/share/nginx/html -s nginx
    0424145638.937 INFO     Connecting to: tiny.20ft.nz
    ...................................
    0424145640.996 INFO     SSH server listening on port: 2222

All good. Fetching the index page gives... ::

    dpreece@davermbp ~> curl http://localhost:8080
    <!DOCTYPE html>
    ....blah blah blah....
    </html>

The fresh volume absorbed the existing files and as a result the container works as it would "out of the box". Now let's change something... ::

    dpreece@davermbp ~> ssh -p 2222 root@localhost
    The programs included with the Debian GNU/Linux system are free software;
    the exact distribution terms for each program are described in the
    individual files in /usr/share/doc/*/copyright.

    Debian GNU/Linux comes with ABSOLUTELY NO WARRANTY, to the extent
    permitted by applicable law.
    root@ctr-dxcXKanL76xS7vHTjjBvjU:~# cat > /usr/share/nginx/html/index.html
    Oh no! I've broken the interwebs!
    ^C
    root@ctr-dxcXKanL76xS7vHTjjBvjU:~# exit
    logout
    Connection to localhost closed.

(we can see the stock nginx image is built on Debian)

And now fetch the index... ::

    dpreece@davermbp ~> curl http://localhost:8080
    Oh no! I've broken the interwebs!

All good. Ctrl-C the instance and start another... ::

    0424145829.679 INFO     Disconnect (code 11): disconnected by user
    ^C0424150050.050 INFO     Exit
    dpreece@davermbp ~> tf -p 8080:80 -m Vz9jfz2pbBqQTW8GsVQ2B8:/usr/share/nginx/html -s nginx
    0424150101.150 INFO     Connecting to: tiny.20ft.nz
    ...................................
    0424150103.168 INFO     SSH server listening on port: 2222

And see if our data persisted... ::

    dpreece@davermbp ~> curl http://localhost:8080
    Oh no! I've broken the interwebs!

Yes. Once more but without the volume, just to test that I didn't modify the source image (or otherwise cheat)... ::

    dpreece@davermbp ~> tf -p 8080:80 nginx
    0424150312.656 INFO     Connecting to: tiny.20ft.nz
    ......................................
    0424150314.565 INFO     Created tunnel object: b'NQdKsC2XifRvYqBLgYCGkR' (8080 -> 80)

And ::

    dpreece@davermbp ~> curl http://localhost:8080
    <!DOCTYPE html>
    ....blah blah blah....
    </html>

All good. Lastly let's delete the volume... ::

    dpreece@davermbp ~> tfvoladm list
    {
      "pVy+I8zLW8GVNh8NbESsF8626ARc2i3yUu0DvIdBsXQ=": [
        "Vz9jfz2pbBqQTW8GsVQ2B8"
      ],
      "z5DBGbW0JLuDlSNAKw0gLJquMajBzKzgH0FW9HsEgnk=": [],
      "zSp2CcFVUfNQB3h82dCXw4CP0gmEBnEzG9B2MjaeZFs=": []
    }
    dpreece@davermbp ~> tfvoladm destroy Vz9jfz2pbBqQTW8GsVQ2B8
    dpreece@davermbp ~>

The 'empty mount point' style is similarly trivial: ::

    dpreece@davermbp ~/2/2/docs> tfvoladm create
    {
      "node": "pVy+I8zLW8GVNh8NbESsF8626ARc2i3yUu0DvIdBsXQ=",
      "volume": "9dLmPsT3LTZKHXN3CJ5kYe"
    }
    dpreece@davermbp ~/2/2/docs> tf -m 9dLmPsT3LTZKHXN3CJ5kYe:/new/mount/point -s alpine
    0424151244.637 INFO     Connecting to: tiny.20ft.nz
    ..............................
    0424151246.789 INFO     SSH server listening on port: 2222

And... ::

    dpreece@davermbp ~> ssh -p 2222 root@localhost
    Welcome to Alpine!

    The Alpine Wiki contains a large amount of how-to guides and general
    information about administrating Alpine systems.
    See <http://wiki.alpinelinux.org>.

    You can setup the system with the command: setup-alpine

    You may change this message by editing /etc/motd.

    ctr-TtNbcu5VCsR62sJwWfLqGn:~# cd /new/mount/point/
    ctr-TtNbcu5VCsR62sJwWfLqGn:/new/mount/point# cat > some_file
    some data
    ^C
    ctr-TtNbcu5VCsR62sJwWfLqGn:/new/mount/point# exit

    dpreece@davermbp ~> ssh -p 2222 root@localhost '/bin/cat /new/mount/point/some_file'
    some data

Writing Pre-Boot Files
======================

With existing container technology it is necessary to write (debug, unit test and document) an in-house boot script that gets added to the stock container to customise it's startup given a set of environment variables. 20ft gets over this problem by writing any updated config files into the container before it boots - effectively a dynamic container image.

For instance - our stock nginx container is fine except we don't want it to log, and we want it to start 8 workers not 1. Here is our replacement config file: ::

    dpreece@davermbp ~> cat nginx.conf.replacement
    user  nginx;
    worker_processes  8;
    pid        /var/run/nginx.pid;
    events {
        worker_connections  1024;
    }
    http {
        include       /etc/nginx/mime.types;
        default_type  application/octet-stream;
        sendfile        on;
        include /etc/nginx/conf.d/*.conf;
    }

We can start nginx using this config file using -f... ::

    dpreece@davermbp ~> tf -f nginx.conf.replacement:/etc/nginx/nginx.conf -s -p 8080:80 nginx
    0424160316.499 INFO     Connecting to: tiny.20ft.nz
    ..................................
    0424160318.614 INFO     SSH server listening on port: 2222

See if our new config file got written... ::

    dpreece@davermbp ~> ssh -p 2222 root@localhost /bin/cat /etc/nginx/nginx.conf
    user  nginx;
    worker_processes  8;
    pid        /var/run/nginx.pid;
    events {
        worker_connections  1024;
    }
    http {
        include       /etc/nginx/mime.types;
        default_type  application/octet-stream;
        sendfile        on;
        include /etc/nginx/conf.d/*.conf;
    }

Yep. And did it start the correct number of workers? ::

    dpreece@davermbp ~> ssh -p 2222 root@localhost /bin/ps fax
      PID TTY      STAT   TIME COMMAND
        1 ?        S      0:00 nginx: master process nginx -g daemon off;
    41073 ?        S      0:00 nginx: worker process
    41074 ?        S      0:00 nginx: worker process
    41076 ?        S      0:00 nginx: worker process
    41075 ?        S      0:00 nginx: worker process
    41094 ?        S      0:00 nginx: worker process
    41151 ?        S      0:00 nginx: worker process
    41176 ?        S      0:00 nginx: worker process
    41134 ?        S      0:00 nginx: worker process
    41305 pts/9    Rs     0:00 /bin/ps fax

Yes. Much easier than reworking the boot script!
