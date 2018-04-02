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

from unittest import TestCase, main
import subprocess
import time
import requests
import socket
import random
import os
import signal
import logging
import shortuuid
from concurrent.futures import ThreadPoolExecutor
from tfnz import Taggable, TaggedCollection
from tfnz.location import Location
from tfnz.container import Container
from tfnz.volume import Volume
from tfnz.docker import Docker
from tfnz.endpoint import Cluster, WebEndpoint
from tfnz.components.postgresql import Postgresql


class TfTest(TestCase):
    location = None
    location_string = "wellington.20ft.nz"
    location_cert = "~/.ssh/catalyst-wellington"

    @classmethod
    def setUpClass(cls):
        # ensure we have all the right images
        images = ['nginx', 'alpine', 'bitnami/apache', 'tfnz/env_test', 'tfnz/ends_test', 'debian', 'postgres:alpine']
        futures = []
        with ThreadPoolExecutor() as executor:
            for image in images:
                futures.append(executor.submit(subprocess.call, (['docker', 'pull', image])))
        [f.result() for f in futures]

        # connect to the location
        cls.location = Location(location=cls.location_string, debug_log=True)

    @classmethod
    def tearDownClass(cls):
        if cls.location is not None:
            cls.location.disconnect()
        cls.location = None

    def test_spawn_awake(self):
        node = TfTest.location.node()
        container = node.spawn_container('bitnami/apache').wait_until_ready()
        self.assertTrue(isinstance(container, Container), 'spawn_container returned the wrong type of object')
        self.assertTrue(container.parent() == node, 'Container has the wrong parent')

        # look for apache having started
        time.sleep(10)
        ps_result = container.run_process('/bin/ps ax')
        self.assertTrue(b'start --foreground apache' in ps_result[0], 'Container didnt boot properly')

        # did it use the right docker config?
        ideal = Docker.description('bitnami/apache')
        self.assertTrue(container.docker_config == ideal, 'Container launched with wrong docker config')

        node.destroy_container(container)

    def test_env_vars(self):
        node = TfTest.location.node()
        container = node.spawn_container('tfnz/env_test', env=[('TEST', 'testy')])
        tunnel = container.wait_http_200()

        # did it pass the environment correctly?
        reply = requests.get('http://127.0.0.1:' + str(tunnel.localport()))
        vars = reply.text.split('\n')
        var_dict = {var.split('=')[0]: var.split('=')[1] for var in vars[:-1]}
        self.assertTrue(var_dict['TEST'] == "testy", "Failed to pass environment variable")

        # do commands have the environment passed?
        stdout, stderr, rtn = container.run_process('echo $TEST')
        self.assertTrue(stdout[:-1] == b'testy', "Failed to pass environment variable to running process")

        container.destroy_tunnel(tunnel)
        node.destroy_container(container)

    def test_spawn_asleep(self):
        # is it asleep?
        node = TfTest.location.node()
        container = node.spawn_container('bitnami/apache', sleep=True)
        time.sleep(5)  # give it a while to boot or fall over
        ps_result = container.run_process('/bin/ps ax')  # tests that we can still run processes
        self.assertTrue('sh' in ps_result[0].decode())
        self.assertTrue('apache' not in ps_result[0].decode())

        # so start it
        container.start()
        time.sleep(5)
        ps_result = container.run_process('/bin/ps ax')
        self.assertTrue('apache' in ps_result[0].decode())

        node.destroy_container(container)

    def test_spawn_preboot(self):
        # sent wrong
        node = TfTest.location.node()
        ctr = None
        preboot = ['/usr/share/nginx/html/index.html', 'Hello World!']
        try:
            node.spawn_container('nginx', pre_boot_files=preboot)
        except ValueError:
            self.assertTrue(True)

        # wrong again
        preboot = [{'/usr/share/nginx/html/index.html': 'Hello World!'}]
        try:
            node.spawn_container('nginx', pre_boot_files=preboot)
        except ValueError:
            self.assertTrue(True)

        # write configuration files before we boot
        preboot = [('/usr/share/nginx/html/index.html', 'Hello World!')]
        container = node.spawn_container('nginx', pre_boot_files=preboot)
        self.assertTrue(b'Hello World!' in container.fetch('/usr/share/nginx/html/index.html'))
        node.destroy_container(container)

    def test_volumes(self):

        def test_termination_callback(obj, returncode):
            self.terminated_volume = obj

        vol = TfTest.location.create_volume(termination_callback=test_termination_callback)
        vol2 = TfTest.location.create_volume()
        try:
            self.assertIsNotNone(vol, 'Volume was not created')

            # delete
            TfTest.location.destroy_volume(vol)
            time.sleep(5)
            self.assertTrue(vol not in TfTest.location.volumes, 'Volume did not disappear from the list of volumes')
            self.assertTrue(self.terminated_volume == vol, 'Volume did not call back to say it had been terminated')

            # delete again should bork
            try:
                TfTest.location.destroy_volume(vol)
                self.assertTrue(False, 'Calling destroy on an already destroyed volume did not throw a value error')
            except ValueError:
                self.assertTrue(True)
            vol = None

            # catching passing the wrong object for volumes when spawning
            node = TfTest.location.node()
            try:
                node.spawn_container('alpine', volumes=(vol2, '/mount/point'))  # deliberately wrong, don't fix!
                self.assertTrue(False, "Did not catch spawn_container being passed the wrong object for volumes")
            except ValueError:
                pass

            # create and mount in a container
            ctr2 = node.spawn_container('alpine', volumes=[(vol2, '/mount/point')])
            ctr2.put('/mount/point/test', b'I am a test')
            self.assertTrue(ctr2.fetch('/mount/point/test') == b'I am a test', "Did not retrieve the same data")

            # don't destroy while mounted
            try:
                TfTest.location.destroy_volume(vol2)
                self.assertTrue(False, "Did not prevent volume from being destroyed while mounted")
            except ValueError:
                pass

            # destroy and mount in a new container
            node.destroy_container(ctr2)
            time.sleep(1)
            ctr3 = node.spawn_container('alpine', volumes=[(vol2, '/mount/point')])
            self.assertTrue(ctr3.fetch('/mount/point/test') == b'I am a test', "Volume not actually persistent")
            node.destroy_container(ctr3)
            time.sleep(1)

            # connect from a second client, destroy a volume to test the callback
            client_session = Location(location=TfTest.location_string)
            client_session_volume = client_session.create_volume(tag='test')
            time.sleep(1)
            found_volume = TfTest.location.volume('test')
            found_volume.termination_callback = test_termination_callback
            client_session.destroy_volume(client_session_volume)
            time.sleep(1)
            client_session.disconnect()
            self.assertTrue(self.terminated_volume == found_volume, 'Did not get termination callback for found volume')
        finally:
            # clean up, for obvious reasons they're not garbage collected :)
            if vol is not None:
                TfTest.location.destroy_volume(vol)
            TfTest.location.destroy_volume(vol2)

    def test_postgres(self):
        vol = TfTest.location.create_volume()
        node = TfTest.location.node()
        postgres = None
        try:
            postgres = Postgresql(node, vol, log_callback=lambda _, l: print(l.decode()))
            postgres.wait_truly_up()
            with open("iso-3166.sql") as f:
                postgres.put('iso-3166.sql', f.read().encode())
            time.sleep(5)
            stdout, stderr, rtn = postgres.run_process('cat iso-3166.sql | psql -Upostgres')
            stdout, stderr, rtn = postgres.run_process('echo "SELECT count(*) FROM subcountry;" | psql -Upostgres')
            self.assertTrue(b'3995' in stdout)
        finally:
            if postgres is not None:
                node.destroy_container(postgres)
                time.sleep(5)  # let it unmount volume before we delete it (which we won't normally do)
            TfTest.location.destroy_volume(vol)

    def test_tagging(self):
        # a tagged object needs a user pk even if it's only for this user
        # has a uuid like everything else, too
        uuid = shortuuid.uuid()
        to = Taggable(TfTest.location.user_pk, uuid)
        uuid2 = shortuuid.uuid()
        to2 = Taggable(TfTest.location.user_pk, uuid2)

        # the object(s) can go in a collection
        col = TaggedCollection([to])  # constructor takes a list of initial objects
        col.add(to2)

        # fetch by uuid
        to_out = col.get(TfTest.location.user_pk, uuid)
        self.assertTrue(to is to_out)

        # fetch by uuid, doesn't need to know the user_pk
        # because the collection retains a list of which users created which uuid's
        # this is necessary for the broker
        to_out2 = col[uuid2]
        self.assertTrue(to2 is to_out2)

        # an actually tagged object
        uuid3 = shortuuid.uuid()
        to3 = Taggable(TfTest.location.user_pk, uuid3, tag='uuid3_tag')
        col.add(to3)

        # using a fluffy string
        to_out3 = col.get(TfTest.location.user_pk, 'uuid3_tag')  # a string is not assumed to be a UUID
        self.assertTrue(to3 is to_out3)
        to_out4 = col.get(TfTest.location.user_pk, uuid3 + ':uuid3_tag')
        self.assertTrue(to3 is to_out4)
        to_out5 = col.get(TfTest.location.user_pk, uuid3)
        self.assertTrue(to3 is to_out5)

    def test_vol_subtree(self):
        current = set()
        current.add('/mount/point')

        # propose a subtree
        i1 = Volume.trees_intersect(current, '/mount/point/subtree')
        self.assertTrue(i1[0] == '/mount/point/subtree' and i1[1] == '/mount/point')

        # propose a supertree
        i2 = Volume.trees_intersect(current, '/mount')
        self.assertTrue(i2[0] == '/mount/point' and i2[1] == '/mount')

        # propose safe
        i3 = Volume.trees_intersect(current, '/mount/different')
        self.assertTrue(i3 is None)

        # mess around with non-normalised paths
        current.add('/mount/different/')
        i4 = Volume.trees_intersect(current, '/mount/point/../tricky/')
        self.assertTrue(i4 is None)
        current.add('/mount/point/../tricky/')
        i5 = Volume.trees_intersect(current, '/mount/point/../tricky/one')
        self.assertTrue(i5[0] == '/mount/tricky/one' and i5[1] == '/mount/tricky')

    def test_sftp(self):
        node = TfTest.location.node()
        ctr = node.spawn_container('alpine', sleep=True).wait_until_ready()
        port = random.randrange(1024, 8192)
        while True:
            try:
                ctr.create_ssh_server(port)
                break
            except RuntimeError:
                port += random.randrange(1024, 8192)

        def sftp_op(command, port):
            sftp = subprocess.Popen(['/usr/bin/sftp',
                                     '-P', str(port),
                                     '-o', 'StrictHostKeyChecking=no',
                                     'root@localhost']
                                    , stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (stdout, stderr) = sftp.communicate(input=command)
            logging.debug("SFTP: " + stdout.decode())
            return stdout

        # upload and retrieve
        self.assertTrue(b'Uploading tf_test.py to /tf_test.py' in sftp_op(b'put tf_test.py', port))
        self.assertTrue(b'Fetching /tf_test.py to tf_test.py.sftp' in sftp_op(b'get /tf_test.py tf_test.py.sftp', port))
        with open('tf_test.py') as f:
            orig = f.read()
        with open('tf_test.py.sftp') as f:
            copied = f.read()
        self.assertTrue(orig == copied)
        subprocess.call(['rm', 'tf_test.py.sftp'])

        # rename
        sftp_op(b'rename tf_test.py tf_test.renamed', port)
        self.assertTrue(b'Fetching /tf_test.renamed to tf_test.renamed' in sftp_op(b'get /tf_test.renamed', port))
        self.assertTrue(os.path.exists('tf_test.renamed'))
        subprocess.call(['rm', 'tf_test.renamed'])

        # delete
        sftp_op(b'rm /tf_test.renamed', port)
        self.assertTrue(b'not found' in sftp_op(b'get /tf_test.renamed', port))

        # mkdir, ls, rmdir
        sftp_op(b'mkdir /unit-test', port)
        self.assertTrue(b'unit-test' in sftp_op(b'ls', port))
        sftp_op(b'rmdir /unit-test', port)
        self.assertFalse(b'unit-test' in sftp_op(b'ls', port))

        node.destroy_container(ctr)

    def test_reboot(self):
        # create a container with some preboot files
        preboot = [('/usr/share/nginx/html/index.html', b'Hello World!')]
        container = TfTest.location.node().spawn_container('nginx', pre_boot_files=preboot)
        tnl = container.wait_http_200()

        # Is it serving the correct file?
        resp = requests.get("http://127.0.0.1:" + str(tnl.localport()))
        self.assertTrue(resp.text == 'Hello World!', "Preboot file apparently not written in")

        # Ensure we're losing changes.
        container.put('/usr/share/nginx/html/index.html', b'Smeg')
        resp = requests.get("http://127.0.0.1:" + str(tnl.localport()))
        self.assertTrue(resp.text == 'Smeg', "Didn't manage to replace preboot file")

        # Reset should take it to after the preboot files and not just the container image
        # Tunnel should still be live
        container.reboot(reset_filesystem=True)
        try:
            resp = requests.get("http://127.0.0.1:" + str(tnl.localport()))
            self.assertTrue(resp.text == 'Hello World!', "Filesystem did not recover")
        except BaseException as e:
            self.assertTrue(False, "test_reboot failed: " + str(e))

    def test_firewalling(self):
        # can we connect one container to another?
        node = TfTest.location.node()
        server = node.spawn_container('nginx')
        client = node.spawn_container('alpine')

        # make the client more clienty
        client.run_process('apk update')
        client.run_process('apk add curl')

        # not yet
        cmd = "curl --connect-timeout 1 http://" + server.ip
        stdout, stderr, exit_code = client.run_process(cmd)
        self.assertTrue(exit_code != 0, "curl should have failed")

        # connect them
        server.allow_connection_from(client)
        time.sleep(1)
        stdout, stderr, exit_code = client.run_process(cmd)
        self.assertTrue(b'Welcome to nginx!' in stdout, 'Did not manage to connect containers')

        # disconnect again
        server.disallow_connection_from(client)
        time.sleep(1)
        stdout, stderr, exit_code = client.run_process(cmd)
        self.assertTrue(exit_code != 0, 'Did not manage to disconnect containers')

        node.destroy_container(client)
        node.destroy_container(server)

        # across nodes?
        nodes = TfTest.location.ranked_nodes()
        if len(nodes) < 2:
            print("WARNING: could not test for cross node firewalling")
            return

        containers = []
        for node in nodes:
            containers.append(node.spawn_container('alpine'))
        for container in containers:
            for target in containers:
                if target is container:
                    continue
                target.wait_until_ready()  # otherwise the ip hasn't been allocated
                cmd = "ping -c 1 -W 1 " + target.ip
                stdout, stderr, exit_code = container.run_process(cmd)
                self.assertTrue(exit_code != 0)
                target.allow_connection_from(container)
                stdout, stderr, exit_code = container.run_process(cmd)
                self.assertTrue(exit_code == 0)
                target.disallow_connection_from(container)

    def test_web_endpoint(self):
        # test and create endpoint
        eps = TfTest.location.endpoints
        if TfTest.location_string not in eps.keys():
            print("WARNING: could not test endpoints, test domain has not been claimed")
            return
        ep = eps[TfTest.location_string]
        fqdn = shortuuid.uuid() + "." + TfTest.location_string
        nodes = TfTest.location.ranked_nodes()

        # create a single server cluster to serve the endpoint
        one = nodes[0].spawn_container('tfnz/env_test', env=[('SERVER', 'one')])
        cluster = Cluster(containers=[one])

        # attach the cluster to the endpoint
        ep.publish(cluster, fqdn)
        WebEndpoint.wait_http_200(fqdn)

        # did it work?
        reply = requests.get('http://' + fqdn)
        self.assertTrue('SERVER=one' in reply.text, 'WebEndpoint failed to publish')

        # add a container to the cluster
        two_node = nodes[1] if len(nodes) > 1 else nodes[0]
        two = two_node.spawn_container('tfnz/env_test', env=[('SERVER', 'two')])
        cluster.add_container(two)

        # add it again makes no difference
        cluster.add_container(two)
        self.assertTrue(len(cluster.containers) == 2)

        # did that work?
        replies = [requests.get('http://' + fqdn).text for _ in range(0, 10)]
        s1 = False
        s2 = False
        for reply in replies:
            if 'SERVER=one' in reply:
                s1 = True
            if 'SERVER=two' in reply:
                s2 = True
        self.assertTrue(s1)
        self.assertTrue(s2, 'WebEndpoint failed add a new server to a cluster')

        # remove a container
        cluster.remove_container(one)
        time.sleep(1)
        replies = [requests.get('http://' + fqdn).text for _ in range(0, 10)]
        s1 = False
        s2 = False
        for reply in replies:
            if 'SERVER=one' in reply:
                s1 = True
            if 'SERVER=two' in reply:
                s2 = True
        self.assertFalse(s1, 'WebEndpoint failed to remove a server from a cluster')
        self.assertTrue(s2)

        # remove it again makes no difference
        cluster.remove_container(one)
        self.assertTrue(len(cluster.containers) == 1)

        # unpublish
        ep.unpublish(cluster)
        try:
            requests.get('http://' + fqdn)
            self.assertTrue(False, 'requests should not have been able to reach the site')
        except:
            pass

        # exit
        nodes[0].destroy_container(one)
        two_node.destroy_container(two)

    def test_web_endpoint_ssl(self):
        # test and create endpoint
        eps = TfTest.location.endpoints
        if TfTest.location_string not in eps.keys():
            print("WARNING: could not test endpoints, test domain has not been claimed")
            return
        ep = eps[TfTest.location_string]

        # create a single server cluster to serve the endpoint
        node = TfTest.location.node()
        nginx = node.spawn_container('nginx')
        cluster = Cluster(containers=[nginx])

        try:
            # create self-signed cert
            fqdn = shortuuid.uuid() + "." + TfTest.location_string
            subprocess.call(['echo "\n\n\n\n\n%s\n\n" | '
                             'openssl req -x509 -nodes -newkey rsa:2048 -keyout key%s.pem -out cert%s.pem' %
                             (fqdn, fqdn, fqdn)], shell=True)

            # attach the cluster to the endpoint
            ep.publish(cluster, fqdn, ssl=('cert%s.pem' % fqdn, 'key%s.pem' % fqdn))

            # did it work?
            time.sleep(1)
            reply = requests.get('https://' + fqdn, verify='cert%s.pem' % fqdn)
            self.assertTrue('Welcome to nginx!' in reply.text, 'WebEndpoint failed to publish')
        finally:
            ep.unpublish(cluster)
            node.destroy_container(nginx)
            subprocess.call(['rm', 'cert%s.pem' % fqdn, 'key%s.pem' % fqdn])

    def test_external_container(self):
        # create a server
        tag = str(int(random.random()*1000000))
        server_node = TfTest.location.node()
        server = server_node.spawn_container('nginx', tag=tag).wait_until_ready()

        # create a client in a separate session
        client_session = Location(location=TfTest.location_string)
        client_node = client_session.node()
        client = client_node.spawn_container('alpine').wait_until_ready()

        # find the server from the second session
        webserver = client_session.external_container(tag)
        webserver.allow_connection_from(client)

        # see if we're a goer
        stdout, stderr, exit_code = client.run_process('wget -O - http://' + webserver.ip)
        self.assertTrue(b'Welcome to nginx!' in stdout, 'Failed to get output from webserver')

        # clean
        client_node.destroy_container(client)
        client_session.disconnect()
        server_node.destroy_container(server)

    def test_state_tracking(self):
        node = TfTest.location.node()

        # containers
        before = len(node.containers)
        c1 = node.spawn_container('alpine', sleep=True).wait_until_ready()
        self.assertTrue(c1 in node.all_containers(), "List of containers on node did not contain right one")
        c2 = node.spawn_container('alpine', sleep=True).wait_until_ready()
        self.assertTrue(c2 in node.all_containers(), "Second container was not in the list of containers")
        self.assertTrue(c1 in node.all_containers(), "First container was no longer on the list of containers")

        # processes
        p1 = c1.spawn_process('ping 8.8.8.8')
        self.assertTrue(p1 in c1.all_processes(), "Did not add the correct process to the process list")
        p2 = c1.spawn_process('ping 8.8.8.8')
        self.assertTrue(p1 in c1.all_processes(), "Lost first process from list of processes")
        self.assertTrue(p2 in c1.all_processes(), "New process was not added to list of processes")
        c1.destroy_process(p2)
        self.assertTrue(p1 in c1.all_processes(), "Removed the wrong process from the process list")
        c1.destroy_process(p1)

        # we now only track containers when they've *actually* gone
        node.destroy_container(c1)
        time.sleep(2)

        self.assertTrue(c2 in node.all_containers(), "Wrong container was removed from list")
        self.assertTrue(c1 not in node.all_containers(), "Wrong container was removed from list (2)")

        # do we know the container is dead?
        try:
            c1.attach_tunnel(80)
        except ValueError:
            self.assertTrue(True)

        # tunnels
        t1 = c2.attach_tunnel(80, localport=8000)
        self.assertTrue(t1 in c2.all_tunnels(), "List of tunnels on container did not contain right one")
        t2 = c2.attach_tunnel(80, localport=8001)
        self.assertTrue(t2 in c2.all_tunnels(), "Second tunnel was not in the list of tunnels")
        self.assertTrue(t1 in c2.all_tunnels(), "First tunnel was no longer on the list of tunnels")
        c2.destroy_tunnel(t1)
        self.assertTrue(t2 in c2.all_tunnels(), "Wrong tunnel was removed from list")
        self.assertTrue(t1 not in c2.all_tunnels(), "Wrong tunnel was removed from list (2)")

        # do we know the tunnel is dead?
        try:
            t2.localport()
        except ValueError:
            self.assertTrue(True)

        # cleaning
        c2.destroy_tunnel(t2)

    def test_multiple_connect(self):
        # should be banned by the geneva convention
        locs = [Location() for _ in range(0, 5)]
        nodes = [loc.node() for loc in locs]
        containers = [node.spawn_container('alpine') for node in nodes]
        self.assertTrue(True)
        for loc in locs:
            loc.disconnect()
        containers.clear()
        locs.clear()

    def test_portscan_connect(self):
        # something somewhere is messing with our socket
        ip = TfTest.location.conn.connect_ip
        socket.create_connection((ip, 2020))
        loc = Location(location=TfTest.location_string)
        ctr = loc.node().spawn_container('alpine', sleep=True).wait_until_ready()  # will not return if broken
        loc.disconnect()

    def test_file_handling(self):
        # tests raising exceptions, too
        node = TfTest.location.node()
        container = node.spawn_container('nginx')

        # upload a new file
        container.put('/usr/share/nginx/html/index.html', b'Hello World')
        self.assertTrue(container.fetch('/usr/share/nginx/html/index.html') == b'Hello World',
                        'New hello world didn\'t upload')

        # upload a new file *and* create a path
        container.put('/a/brand/new/path/test', b'New Path Test')
        self.assertTrue(container.fetch('/a/brand/new/path/test') == b'New Path Test', 'New path test failed')

        # try to reference outside the container
        try:
            container.put('../what.ever', b'Some Data')
            self.assertTrue(False, 'Trying to put outside the container did not throw an exception')
        except ValueError:
            self.assertTrue(True)

        # exists but is a directory
        try:
            container.fetch('/usr')
            self.assertTrue(False, 'Trying to fetch a directory did not throw an excepton')
        except ValueError as e:
            self.assertTrue(True)

        node.destroy_container(container)

    def test_spawn_process(self):
        # This test fails if noodle is running in the debugger
        node = TfTest.location.node()
        container = node.spawn_container('debian', sleep=True)

        # test command styles
        r1 = container.run_process('/bin/echo Hello World')[0]
        self.assertTrue(r1 == b'Hello World\n')
        try:
            # not passing lists any more
            container.run_process(['/bin/echo', 'Hello World'])
            self.assertTrue(False)
        except ValueError:
            pass

        node.destroy_container(container)

    def test_callbacks_shell(self):
        self.terminated_process = None

        self.test_data = b''
        def test_data_callback(obj, data):
            self.test_data += data

        def test_termination_callback(obj, returncode):
            self.terminated_process = obj

        node = TfTest.location.node()
        alpine_container = node.spawn_container('alpine')

        # a long lived process test asynchronous results
        long_process = alpine_container.spawn_process('iostat -c 1', data_callback=test_data_callback)

        # a short process tests termination
        short_process = alpine_container.spawn_process('sleep 1', termination_callback=test_termination_callback)
        time.sleep(2)
        self.assertTrue(self.terminated_process is short_process, 'Termination callbacks not working')

        # worked asynchronously
        snapshot = bytes(self.test_data)
        if b'avg-cpu' not in snapshot:
            lines = snapshot.count(b'\n')
            self.assertTrue(lines != 0, 'Data callbacks not working')

        # destroys
        alpine_container.destroy_process(long_process)
        time.sleep(2)  # time to actually stop
        self.test_data = b''
        time.sleep(2)  # give it a chance to go wrong
        destroyed_lines = self.test_data.count(b'\n')
        self.assertTrue(destroyed_lines == 0, 'Destroying a long running process didn\'t work')

        # works for a shell
        shell = alpine_container.spawn_shell(data_callback=test_data_callback,
                                             termination_callback=test_termination_callback)
        shell.stdin(b'uname -v\n')
        time.sleep(2)  # otherwise we kill the process before it's had time to return
        alpine_container.destroy_process(shell)
        time.sleep(1)  # otherwise we test for termination before it's had time to terminate
        self.assertTrue(b'Debian' in self.test_data, "Did not apparently shell in")
        self.assertTrue(self.terminated_process is shell, 'Shell did not call termination callback')

        # being informed of the termination of a process because it was inside a container that was destroyed
        proc = alpine_container.spawn_process('sleep 1000000', termination_callback=test_termination_callback)
        time.sleep(1)
        node.destroy_container(alpine_container)
        time.sleep(1)
        self.assertTrue(self.terminated_process == proc, 'Destroyed process (due to container) callback not working')

    def test_background_blocking_calls(self):
        self.background_call_completed = False

        def test_termination_callback(obj, returncode):
            pong = TfTest.location.conn.send_blocking_cmd(b'ping')
            self.background_call_completed = True

        node = TfTest.location.node()
        alpine_container = node.spawn_container('alpine')
        alpine_container.spawn_process('sleep 1', termination_callback=test_termination_callback)
        time.sleep(5)
        self.assertTrue(self.background_call_completed, "The background blocking call did not return")

    def test_process_interact(self):
        self.sh_data = b''

        def test_interactive_callback(obj, data):
            self.sh_data += data

        node = TfTest.location.node()
        container = node.spawn_container('alpine', sleep=True)
        ash = container.spawn_process('sh', data_callback=test_interactive_callback)
        time.sleep(1)
        self.sh_data = b''
        ash.stdin('echo "---hi---"\n'.encode())
        time.sleep(1)
        self.assertTrue(b'hi' in self.sh_data, "Asynchronous return did not apparently send data")
        async = self.sh_data
        self.sh_data = b''
        container.destroy_process(ash)
        node.destroy_container(container)

    def test_container_terminates(self):
        self.terminate_data = None

        def test_terminates_callback(obj, returncode):
            self.terminate_data = obj

        node = TfTest.location.node()
        container = node.spawn_container('tfnz/ends_test', termination_callback=test_terminates_callback)
        time.sleep(10)
        self.assertTrue(self.terminate_data == container, "Termination callback was not called")

    def test_tunnels_http(self):
        node = TfTest.location.node()
        container = node.spawn_container('nginx')

        # creating a tunnel after http 200
        tnl = container.wait_http_200()
        reply = requests.get('http://127.0.0.1:' + str(tnl.localport()))
        self.assertTrue('Welcome to nginx!' in reply.text, 'Did not get the expected reply from container')

        node.destroy_container(container)

    def test_contain_loop(self):
        self._destructive_behaviour('dd if=/dev/zero of=/dev/null')

    def test_contain_cat(self):
        self._destructive_behaviour('dd if=/dev/zero of=/zeroes bs=1M')

    def test_contain_fork_bomb(self):
        self._destructive_behaviour("bomb.sh",
                                    ["sh -c \"echo \'sh \$0 & sh \$0\' > bomb.sh\"", 'chmod +x bomb.sh'],
                                    'debian')

    def test_contain_malloc(self):
        self._destructive_behaviour("python3 -c '[bytearray(1024) for _ in range(0, 1000000)]'",
                                    ['apk update', 'apk add python3'])

    def _destructive_behaviour(self, spawn, pre_run=None, image='alpine'):
        if pre_run is None:
            pre_run = []
        node = TfTest.location.node()
        logging.debug("Destructive behaviour: " + spawn)

        # bad container does a bad thing, does it prevent good container from booting?
        bad_container = node.spawn_container(image)
        good_container = None

        # do we have some stuff to do before we're bad?
        try:
            for cmd in pre_run:
                bad_container.run_process(cmd)
            procs = [bad_container.spawn_process(spawn) for _ in range(0, 2)]
            logging.debug("Running procs: " + str(procs))
            time.sleep(10)
            start = time.time()
            logging.debug("Starting another container, waiting until ready.")
            good_container = node.spawn_container('alpine').wait_until_ready()  # will throw if a problem
            logging.debug("Container startup time: " + str(time.time() - start))
        finally:
            node.destroy_container(bad_container)
            if good_container is not None:
                node.destroy_container(good_container)


if __name__ == '__main__':
    main()
