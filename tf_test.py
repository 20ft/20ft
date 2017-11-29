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
import os.path
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from tfnz.location import Location, RankBias
from tfnz.container import Container
from tfnz.volume import Volume
from tfnz.docker import Docker
from tfnz.endpoint import Cluster


class TfTest(TestCase):
    location = None
    location_string = "sydney.20ft.nz"
    location_cert = "~/.ssh/aws_sydney.pem"
    disable_laksa_restart = True

    @classmethod
    def setUpClass(cls):
        # # ensure we have all the right images
        # images = ['nginx', 'alpine', 'bitnami/apache', 'tfnz/env_test', 'tfnz/ends_test', 'debian']
        # futures = []
        # with ThreadPoolExecutor() as executor:
        #     for image in images:
        #         futures.append(executor.submit(subprocess.call, (['docker', 'pull', image])))
        # [f.result() for f in futures]

        # connect to the location
        cls.location = Location(location=cls.location_string)

    @classmethod
    def tearDownClass(cls):
        cls.location.disconnect()
        cls.location = None

    def test_node(self):
        nodes = TfTest.location.ranked_nodes(bias=RankBias.memory)
        self.assertTrue(len(nodes) > 0, 'No nodes are live, testing is not going to go well')
        if len(nodes) == 0:
            return
        self.assertTrue(nodes[0].parent() == TfTest.location, 'Node has the wrong parent')
        if len(nodes) == 1:
            return

        # test ranking
        nodes = TfTest.location.ranked_nodes(bias=RankBias.memory)
        self.assertTrue(nodes[0].stats['memory'] >= nodes[1].stats['memory'], 'Node ranking is wrong for memory')

        nodes = TfTest.location.ranked_nodes(bias=RankBias.cpu)
        self.assertTrue(nodes[0].stats['cpu'] >= nodes[1].stats['cpu'], 'Node ranking is wrong for cpu')

    def test_spawn_awake(self):
        node = TfTest.location.ranked_nodes()[0]
        container = node.spawn_container('bitnami/apache').wait_until_ready()
        self.assertTrue(isinstance(container, Container), 'spawn_container returned the wrong type of object')
        self.assertTrue(container.parent() == node, 'Container has the wrong parent')

        # look for apache having started
        time.sleep(5)
        ps_result = container.run_process('/bin/ps ax')
        self.assertTrue(b'start --foreground apache' in ps_result[0], 'Container didnt boot properly')

        # did it use the right docker config?
        ideal = Docker.description('bitnami/apache')
        del ideal['ContainerConfig']  # we ditch this because it's duplicated
        self.assertTrue(container.docker_config == ideal, 'Container launched with wrong docker config')

    def test_env_vars(self):
        container = TfTest.location.ranked_nodes()[0].spawn_container('tfnz/env_test', env=[('TEST', 'testy')])
        tunnel = container.wait_http_200()

        # did it pass the environment correctly?
        reply = requests.get('http://127.0.0.1:' + str(tunnel.localport()))
        vars = reply.text.split('\n')
        var_dict = {var.split('=')[0]: var.split('=')[1] for var in vars[:-1]}
        self.assertTrue(var_dict['TEST'] == "testy", "Failed to pass environment variable")
        container.destroy_tunnel(tunnel)

    def test_spawn_asleep(self):
        # is it asleep?
        container = TfTest.location.ranked_nodes()[0].spawn_container('bitnami/apache', sleep=True)
        time.sleep(5)  # give it a while to boot or fall over
        ps_result = container.run_process('/bin/ps ax')  # tests that we can still run processes
        self.assertTrue('sh' in ps_result[0].decode())

    def test_spawn_preboot(self):
        # sent wrong
        preboot = ['/usr/share/nginx/html/index.html', 'Hello World!']
        try:
            TfTest.location.ranked_nodes()[0].spawn_container('nginx', pre_boot_files=preboot)
        except ValueError:
            self.assertTrue(True)

        # wrong again
        preboot = [{'/usr/share/nginx/html/index.html': 'Hello World!'}]
        try:
            TfTest.location.ranked_nodes()[0].spawn_container('nginx', pre_boot_files=preboot)
        except ValueError:
            self.assertTrue(True)

        # write configuration files before we boot
        preboot = [('/usr/share/nginx/html/index.html', 'Hello World!')]
        container = TfTest.location.ranked_nodes()[0].spawn_container('nginx', pre_boot_files=preboot)
        self.assertTrue(b'Hello World!' in container.fetch('/usr/share/nginx/html/index.html'))

    def test_volumes(self):
        vol = TfTest.location.create_volume()
        vol2 = TfTest.location.create_volume()
        try:
            self.assertIsNotNone(vol, 'Volume was not created')

            # delete
            TfTest.location.destroy_volume(vol)
            self.assertTrue(vol not in TfTest.location.volumes, 'Volume did not disappear from the list of volumes')

            # delete again should bork
            try:
                TfTest.location.destroy_volume(vol)
                self.assertTrue(False, 'Calling destroy on an already destroyed volume did not throw a value error')
            except ValueError:
                self.assertTrue(True)
            vol = None

            # catching passing the wrong object for volumes when spawning
            node = TfTest.location.ranked_nodes()[0]
            try:
                node.spawn_container('alpine', volumes=(vol2, '/mount/point'))  # deliberately wrong, don't fix!
                self.assertTrue(False, "Did not catch spawn_container being passed the wrong object for volumes")
            except ValueError:
                pass

            # create and mount in a container
            ctr2 = node.spawn_container('alpine', volumes=[(vol2, '/mount/point')])
            ctr2.put('/mount/point/test', b'I am a test')
            self.assertTrue(ctr2.fetch('/mount/point/test') == b'I am a test', "Did not retrieve the same data")

            # destroy and mount in a new container
            node.destroy_container(ctr2)
            time.sleep(1)
            ctr3 = node.spawn_container('alpine', volumes=[(vol2, '/mount/point')])
            self.assertTrue(ctr3.fetch('/mount/point/test') == b'I am a test', "Volume not actually persistent")
            node.destroy_container(ctr3)
        finally:
            # clean up, for obvious reasons they're not garbage collected :)
            if vol is not None:
                TfTest.location.destroy_volume(vol)
            TfTest.location.destroy_volume(vol2)

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
        node = TfTest.location.ranked_nodes()[0]
        ctr = node.spawn_container('alpine', sleep=True).wait_until_ready()
        ctr.create_ssh_server(2222)

        def sftp_op(command):
            sftp = subprocess.Popen(['/usr/bin/sftp', '-P', '2222', 'root@localhost']
                                    , stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (stdout, stderr) = sftp.communicate(input=command)
            return stdout

        # upload and retrieve
        self.assertTrue(b'Uploading tf_test.py to /tf_test.py' in sftp_op(b'put tf_test.py'))
        self.assertTrue(b'Fetching /tf_test.py to tf_test.py.sftp' in sftp_op(b'get /tf_test.py tf_test.py.sftp'))
        with open('tf_test.py') as f:
            orig = f.read()
        with open('tf_test.py.sftp') as f:
            copied = f.read()
        self.assertTrue(orig == copied)
        subprocess.call(['rm', 'tf_test.py.sftp'])

        # rename
        sftp_op(b'rename tf_test.py tf_test.renamed')
        self.assertTrue(b'Fetching /tf_test.renamed to tf_test.renamed' in sftp_op(b'get /tf_test.renamed'))
        self.assertTrue(os.path.exists('tf_test.renamed'))
        subprocess.call(['rm', 'tf_test.renamed'])

        # delete
        sftp_op(b'rm /tf_test.renamed')
        self.assertTrue(b'not found' in sftp_op(b'get /tf_test.renamed'))

        # mkdir, ls, rmdir
        sftp_op(b'mkdir /unit-test')
        self.assertTrue(b'unit-test' in sftp_op(b'ls'))
        sftp_op(b'rmdir /unit-test')
        self.assertFalse(b'unit-test' in sftp_op(b'ls'))

    def test_reboot(self):
        # create a container with some preboot files
        preboot = [('/usr/share/nginx/html/index.html', b'Hello World!')]
        container = TfTest.location.ranked_nodes()[0].spawn_container('nginx', pre_boot_files=preboot)
        tnl = container.wait_http_200()

        # Is it serving the correct file?
        resp = requests.get("http://127.0.0.1:" + str(tnl.localport()))
        self.assertTrue(resp.text == 'Hello World!', "Preboot file apparently not written in")

        # Broken?
        container.put('/usr/share/nginx/html/index.html', b'Smeg')
        resp = requests.get("http://127.0.0.1:" + str(tnl.localport()))
        self.assertTrue(resp.text == 'Smeg', "Didn't manage to replace preboot file")

        # Reset should take it to after the preboot files and not just the container image
        container.reboot(reset_filesystem=True)
        container.wait_http_200()
        resp = requests.get("http://127.0.0.1:" + str(tnl.localport()))
        self.assertTrue(resp.text == 'Hello World!', "Filesystem did not recover")

    def test_firewalling(self):
        # can we connect one container to another?
        server = TfTest.location.ranked_nodes()[0].spawn_container('nginx')
        client = TfTest.location.ranked_nodes()[0].spawn_container('alpine')

        # make the client more clienty
        client.run_process('apk update')
        client.run_process('apk add curl')

        # not yet
        cmd = "curl --connect-timeout 1 http://" + server.ip
        stdout, stderr, exit_code = client.run_process(cmd)
        self.assertTrue(exit_code != 0, "curl should have failed")

        # connect them
        server.allow_connection_from(client)
        stdout, stderr, exit_code = client.run_process(cmd)
        self.assertTrue(b'Welcome to nginx!' in stdout, 'Did not manage to connect containers')

        # disconnect again
        server.disallow_connection_from(client)
        time.sleep(0.1)
        stdout, stderr, exit_code = client.run_process(cmd)
        self.assertTrue(exit_code != 0, 'Did not manage to disconnect containers')

        # across nodes?
        nodes = TfTest.location.ranked_nodes()
        if len(nodes) < 2:
            print("WARNING: could not test for cross node firewalling")
            return

        containers = []
        for node in nodes:
            containers.append(node.spawn_container('nginx'))
        for container in containers:
            for target in containers:
                if target is container:
                    continue
                cmd = "ping -c 1 -W 1 " + target.ip
                stdout, stderr, exit_code = container.run_process(cmd)
                self.assertTrue(exit_code != 0)
                target.allow_connection_from(container)
                stdout, stderr, exit_code = container.run_process(cmd)
                self.assertTrue(exit_code == 1)
                target.disallow_connection_from(container)

    def test_web_endpoint(self):
        # test and create endpoint
        eps = TfTest.location.endpoints
        if TfTest.location_string not in eps.keys():
            print("WARNING: could not test endpoints, test domain has not been claimed")
            return
        ep = eps[TfTest.location_string]

        # create a single server cluster to serve the endpoint
        nginx = TfTest.location.ranked_nodes()[0].spawn_container('nginx')
        cluster = Cluster([nginx])

        # attach the cluster to the endpoint
        ep.publish(cluster, TfTest.location_string)

        # did it work?
        reply = requests.get('http://' + TfTest.location_string)
        self.assertTrue('Welcome to nginx!' in reply.text, 'WebEndpoint failed to publish')

        ep.unpublish(cluster)

    def test_web_endpoint_ssl(self):
        # test and create endpoint
        eps = TfTest.location.endpoints
        if TfTest.location_string not in eps.keys():
            print("WARNING: could not test endpoints, test domain has not been claimed")
            return
        ep = eps[TfTest.location_string]

        cluster = None
        try:
            # create self-signed cert
            subprocess.call(['echo "\n\n\n\n\n%s\n\n" | '
                             'openssl req -x509 -nodes -newkey rsa:1024 -keyout key.pem -out cert.pem' %
                             TfTest.location_string], shell=True)

            # create a single server cluster to serve the endpoint
            nginx = TfTest.location.ranked_nodes()[0].spawn_container('nginx')
            cluster = Cluster([nginx])

            # attach the cluster to the endpoint
            ep.publish(cluster, TfTest.location_string, ssl=('cert.pem', 'key.pem'))

            # did it work?
            reply = requests.get('https://' + TfTest.location_string, verify='cert.pem')
            self.assertTrue('Welcome to nginx!' in reply.text, 'WebEndpoint failed to publish')
        finally:
            ep.unpublish(cluster)
            subprocess.call(['rm', 'cert.pem', 'key.pem'])

    def test_external_container(self):
        # create a server
        server_node = TfTest.location.ranked_nodes()[0]
        server = server_node.spawn_container('nginx', advertised_tag='webserver').wait_until_ready()

        # create a client in a separate session
        client_session = Location(location=TfTest.location_string)
        client_node = client_session.ranked_nodes()[0]
        client = client_node.spawn_container('alpine').wait_until_ready()

        # find the server from the second session
        webserver = client_session.container_for('webserver')
        webserver.allow_connection_from(client)

        # see if we're a goer
        stdout, stderr, exit_code = client.run_process('wget -O - http://' + webserver.ip)
        self.assertTrue(b'Welcome to nginx!' in stdout, 'Failed to get output from webserver')

        # clean
        client_node.destroy_container(client)
        client_session.disconnect()
        server_node.destroy_container(server)

    def test_state_tracking(self):
        node = TfTest.location.ranked_nodes()[0]

        # containers
        before = len(node.all_containers())
        c1 = node.spawn_container('alpine', sleep=True).wait_until_ready()
        self.assertTrue(len(node.all_containers()) == before + 1, "List of containers on a node was wrong")
        self.assertTrue(c1 in node.all_containers(), "List of containers on node did not contain right one")
        c2 = node.spawn_container('alpine', sleep=True).wait_until_ready()
        self.assertTrue(len(node.all_containers()) == before + 2, "List of containers on a node did not get larger")
        self.assertTrue(c2 in node.all_containers(), "Second container was not in the list of containers")
        self.assertTrue(c1 in node.all_containers(), "First container was no longer on the list of containers")

        # processes
        p1 = c1.spawn_process('ping 8.8.8.8')
        self.assertTrue(len(c1.all_processes()) == 1, "List of processes was wrong")
        self.assertTrue(p1 in c1.all_processes(), "Did not add the correct process to the process list")
        p2 = c1.spawn_process('ping 8.8.8.8')
        self.assertTrue(len(c1.all_processes()) == 2, "List of processes did not grow")
        self.assertTrue(p1 in c1.all_processes(), "Lost first process from list of processes")
        self.assertTrue(p2 in c1.all_processes(), "New process was not added to list of processes")
        c1.destroy_process(p2)
        self.assertTrue(len(c1.all_processes()) == 1, "List of processes did not shrink")
        self.assertTrue(p1 in c1.all_processes(), "Removed the wrong process from the process list")
        c1.destroy_process(p1)

        # we now only track containers when they've *actually* gone
        node.destroy_container(c1)
        attempts = 100
        while attempts > 0:
            if len(node.all_containers()) == before + 1:
                break
            if attempts == 0:
                self.assertTrue(False, "List of containers did not remove entry after destroying one")
            time.sleep(0.1)
            attempts -= 1

        self.assertTrue(len(node.all_containers()) == before + 1, "List of containers on a node was wrong after destroying one")
        self.assertTrue(c2 in node.all_containers(), "Wrong container was removed from list")
        self.assertTrue(c1 not in node.all_containers(), "Wrong container was removed from list (2)")

        # do we know the container is dead?
        try:
            c1.attach_tunnel(80)
        except ValueError:
            self.assertTrue(True)

        # tunnels
        t1 = c2.attach_tunnel(80)
        self.assertTrue(len(c2.all_tunnels()) == 1, "List of tunnels on a container was wrong")
        self.assertTrue(t1 in c2.all_tunnels(), "List of tunnels on container did not contain right one")
        t2 = c2.attach_tunnel(80)
        self.assertTrue(len(c2.all_tunnels()) == 2, "List of tunnels on a container did not get larger")
        self.assertTrue(t2 in c2.all_tunnels(), "Second tunnel was not in the list of tunnels")
        self.assertTrue(t1 in c2.all_tunnels(), "First tunnel was no longer on the list of tunnels")
        c2.destroy_tunnel(t1)
        self.assertTrue(len(c2.all_tunnels()) == 1, "List of tunnels on a container was wrong after destroying one")
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
        locs = [Location() for n in range(0, 5)]
        nodes = [loc.ranked_nodes()[0] for loc in locs]
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
        ctr = loc.ranked_nodes()[0].spawn_container('alpine', sleep=True).wait_until_ready()  # will not return if broken
        loc.disconnect()

    def test_file_handling(self):
        # tests raising exceptions, too
        container = TfTest.location.ranked_nodes()[0].spawn_container('nginx')

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

    def test_spawn_process(self):
        # This test fails if noodle is running in the debugger
        container = TfTest.location.ranked_nodes()[0].spawn_container('debian', sleep=True)

        # test command styles
        r1 = container.run_process('/bin/echo Hello World')[0]
        self.assertTrue(r1 == b'Hello World\n')
        try:
            # not passing lists any more
            container.run_process(['/bin/echo', 'Hello World'])
            self.assertTrue(False)
        except ValueError:
            pass

    def test_callbacks_shell(self):
        self.terminated_process = None

        def test_data_callback(obj, data):
            self.test_data += data

        def test_termination_callback(obj):
            self.terminated_process = obj

        node = TfTest.location.ranked_nodes()[0]
        alpine_container = node.spawn_container('alpine').wait_until_ready()

        # a long lived process test asynchronous results
        self.test_data = b''
        long_process = alpine_container.spawn_process('iostat -c 1', data_callback=test_data_callback)

        # a short process tests termination
        short_process = alpine_container.spawn_process('sleep 1', termination_callback=test_termination_callback)
        time.sleep(2)
        self.assertTrue(self.terminated_process is short_process, 'Termination callbacks not working')

        # worked asynchronously
        snapshot = bytes(self.test_data)
        if b'.pycharm_helpers' not in snapshot:
            lines = snapshot.count(b'\n')
            self.assertTrue(lines != 0, 'Data callbacks not working')

        # destroys
        alpine_container.destroy_process(long_process)
        time.sleep(1)  # time to actually stop
        self.test_data = b''
        time.sleep(1)  # give it a chance to go wrong
        destroyed_lines = self.test_data.count(b'\n')
        self.assertTrue(destroyed_lines == 0, 'Destroying a long running process didn\'t work')

        # works for a shell
        self.test_data = b''
        shell = alpine_container.spawn_shell(data_callback=test_data_callback,
                                             termination_callback=test_termination_callback)
        shell.stdin(b'/bin/ps faxu\n')
        time.sleep(3)
        alpine_container.destroy_process(shell)
        self.assertTrue(b'iostat -c 1' in self.test_data, "Did not apparently shell in")
        self.assertTrue(self.terminated_process is shell, 'Shell did not call termination callback')

        # being informed of the termination of a process because it was inside a container that was destroyed
        proc = alpine_container.spawn_process('sleep 1000000', termination_callback=test_termination_callback)
        time.sleep(1)
        node.destroy_container(alpine_container)
        time.sleep(1)
        self.assertTrue(self.terminated_process == proc, 'Destroyed process (due to container) callback not working')

    def test_process_interact(self):
        self.sh_data = b''

        def test_interactive_callback(obj, data):
            self.sh_data += data

        container = TfTest.location.ranked_nodes()[0].spawn_container('alpine', sleep=True)
        ash = container.spawn_process('sh', data_callback=test_interactive_callback)
        time.sleep(1)
        self.sh_data = b''
        ash.stdin('echo "---hi---"\n'.encode())
        time.sleep(1)
        self.assertTrue(b'hi' in self.sh_data, "Asynchronous return did not apparently send data")
        async = self.sh_data
        self.sh_data = b''

    def test_container_terminates(self):
        self.terminate_data = None

        def test_terminates_callback(obj):
            self.terminate_data = obj

        container = TfTest.location.ranked_nodes()[0].spawn_container('tfnz/ends_test',
                                                                termination_callback=test_terminates_callback)
        time.sleep(10)
        self.assertTrue(self.terminate_data == container, "Termination callback was not called")

    def test_laksa_restart(self):
        # I CAN NOT MAKE THIS WORK.
        # But it runs off the cli just fine. Something about test stubs?
        if TfTest.disable_laksa_restart:
            return

        # needs automated ssh onto location to pass
        container = TfTest.location.ranked_nodes()[0].spawn_container('tfnz/env_test')
        tunnel = container.wait_http_200()
        reply = requests.get('http://127.0.0.1:' + str(tunnel.localport()))
        self.assertTrue('PATH' in reply.text, "Initial server reply failed")

        # disable
        subprocess.call(['ssh', '-i', TfTest.location_cert, 'admin@' + TfTest.location_string,
                         'sudo systemctl stop laksa'])
        time.sleep(5)
        try:
            requests.get('http://127.0.0.1:' + str(tunnel.localport()), timeout=2)
            self.assertTrue(False, "Request should've timed out")
        except requests.exceptions.ReadTimeout:
            pass

        # restart
        subprocess.call(['ssh', '-i', TfTest.location_cert, 'admin@' + TfTest.location_string,
                         'sudo systemctl start laksa'])
        time.sleep(5)
        reply = requests.get('http://127.0.0.1:' + str(tunnel.localport()))
        self.assertTrue('PATH' in reply.text, "Server did not reconnect transparently")

    def test_tunnels_http(self):
        node = TfTest.location.ranked_nodes()[0]
        container = node.spawn_container('nginx')

        # creating a tunnel after http 200
        tnl = container.wait_http_200()
        reply = requests.get('http://127.0.0.1:' + str(tnl.localport()))
        self.assertTrue('Welcome to nginx!' in reply.text, 'Did not get the expected reply from container')

        # being a pain about it
        tunnels = []
        for i in range(0, 10):
            if random.randint(0, 1) == 0:
                container.attach_tunnel(80)
            else:
                tunnels = container.all_tunnels()
                if len(tunnels) != 0:
                    idx = random.randint(0, len(tunnels) - 1)
                    container.destroy_tunnel(tunnels[idx])

        node.destroy_container(container)

    def test_contain_loop(self):
        self._destructive_behaviour('dd if=/dev/zero of=/dev/null')

    def test_contain_cat(self):
        self._destructive_behaviour('dd if=/dev/zero of=/zeroes bs=1M')

    def test_contain_fork_bomb(self):
        self._destructive_behaviour("sh bomb.sh",
                                    ["sh -c \"echo \'sh $0 & sh $0\' > bomb.sh\"", 'chmod +x bomb.sh'])

    def test_contain_malloc(self):
        self._destructive_behaviour("python3 -c '[bytearray(1024) for _ in range(0, 1000000)]'",
                                    ['apk update', 'apk add python3'])

    def _destructive_behaviour(self, spawn, pre_run=None):
        if pre_run is None:
            pre_run = []
        node = TfTest.location.ranked_nodes()[0]
        logging.debug("Destructive behaviour: " + spawn)

        # bad container does a bad thing, does it prevent good container from booting?
        bad_container = node.spawn_container('alpine')

        # do we have some stuff to do before we're bad?
        for cmd in pre_run:
            bad_container.run_process(cmd)
        for thread in range(0, 4):
            bad_container.spawn_process(spawn)
        logging.debug("....allowing 10 seconds for things to go pear shaped.")
        time.sleep(10)
        start = time.time()
        logging.debug("....starting another container.")
        good_container = node.spawn_container('alpine').wait_until_ready()  # will throw if a problem
        logging.debug("Container startup time: " + str(time.time() - start))
        node.destroy_container(good_container)
        node.destroy_container(bad_container)


set_unset = None
updated_key = None
updated_value = None

if __name__ == '__main__':
    main()
