# (c) David Preece 2017
# davep@polymath.tech : https://polymath.tech/
"""Unit test and kinda documentation on 20ft"""

# brew install libsodium zeromq
# pip3 install tfnz

from unittest import TestCase, main
import subprocess
import json
import time
from tfnz.location import Location
from tfnz.container import Container
from tfnz import description


class TfTest(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.image = 'nginx'
        cls.launched_process = 'nginx: worker process'
        cls.root_reply_contains = '<title>Welcome to nginx!</title>'
        cls.acceptable_boot_time = 10
        cls.location = Location(debug_log=True)
        cls.location.ensure_image_uploaded(cls.image)

    def test_node(self):
        nodes = TfTest.location.ranked_nodes()
        self.assertTrue(len(nodes) > 0, 'No nodes are live, testing is not going to go well')
        if len(nodes) == 0:
            return
        self.assertTrue(nodes[0].parent() == TfTest.location, 'Node has the wrong parent')
        if len(nodes) == 1:
            return
        self.assertTrue(nodes[0].stats['cpu'] > nodes[1].stats['cpu'], 'Node ranking is wrong')
        self.assertTrue(self.location.best_node() == nodes[0], 'Not reporting the best node and top of rank the same')

    def test_spawn_awake(self):
        node = TfTest.location.best_node()
        container = node.spawn(TfTest.image, no_image_check=True)
        self.assertTrue(isinstance(container, Container), '.spawn returned the wrong type of object')
        self.assertTrue(container.parent() == node, 'Container has the wrong parent')

        # look for nginx having started
        attempts = 0
        while True:
            ps_result = container.spawn_process('ps ax').wait_until_complete()
            running = TfTest.launched_process.encode() in ps_result
            if running:
                self.assertTrue(True, 'Container spawned process')
                break
            attempts += 1
            if attempts == TfTest.acceptable_boot_time:
                self.assertTrue(False, 'Container process failed to spawn')
                break
            time.sleep(1)

        # did it use the right docker config?
        ideal = description(TfTest.image)
        del ideal['ContainerConfig']  # we ditch this because it's duplicated
        self.assertTrue(json.dumps(container.docker_config) == json.dumps(ideal),
                        'Container launched with wrong docker config')

    def test_spawn_asleep(self):
        # is it asleep?
        container = TfTest.location.best_node().spawn(TfTest.image, sleep=True, no_image_check=True)
        time.sleep(TfTest.acceptable_boot_time)  # give it a while to boot or whatever
        ps_result = container.spawn_process('ps ax').wait_until_complete()  # tests that we can still run processes
        self.assertTrue(TfTest.launched_process.encode('ascii') not in ps_result,
                        'Asked for an asleep container but it started anyway')
        self.assertTrue('sleep' in ps_result.decode(), 'The sleep command does not appear to be running')

    def test_spawn_preboot(self):
        # write configuration files before we boot
        preboot = {'/usr/share/nginx/html/index.html': 'Hello World!'}
        container = TfTest.location.best_node().spawn(TfTest.image, pre_boot_files=preboot, no_image_check=True)
        self.assertTrue(b'Hello World!' in container.fetch('/usr/share/nginx/html/index.html'))

    def test_firewalling(self):
        # can we connect one container to another?
        server = TfTest.location.best_node().spawn(TfTest.image, no_image_check=True)
        client = TfTest.location.best_node().spawn(TfTest.image, sleep=True, no_image_check=True)
        # not yet
        cmd = "/native/usr/bin/wget -T 1 -t 1 -O /dev/null http://" + server.ip()
        while True:
            time.sleep(1)
            reply = client.spawn_process(cmd).wait_until_complete().decode()
            if "Network is down" not in reply:
                break
        self.assertTrue("timed out" in reply, 'Should not have got a reply')
        # connect them
        server.allow_connection_from(client)
        reply = client.spawn_process(cmd).wait_until_complete().decode()
        self.assertTrue("'/dev/null' saved" in reply, 'Did not manage to connect containers')
        # disconnect again
        server.disallow_connection_from(client)
        reply = client.spawn_process(cmd).wait_until_complete().decode()
        self.assertTrue("timed out" in reply, 'Did not manage to disconnect containers')

    def test_state_tracking(self):
        # TODO: WTF, this test passes every time when run on it's own
        loc = Location()
        node = loc.best_node()

        # containers
        c1 = node.spawn(TfTest.image, no_image_check=True)
        self.assertTrue(len(node.all_containers()) == 1, "List of containers on a node was wrong")
        self.assertTrue(node.all_containers()[0] == c1, "List of containers on node did not contain right one")
        c2 = node.spawn(TfTest.image, no_image_check=True)
        self.assertTrue(len(node.all_containers()) == 2, "List of containers on a node did not get larger")
        self.assertTrue(c2 in node.all_containers(), "Second container was not in the list of containers")
        self.assertTrue(c1 in node.all_containers(), "First container was no longer on the list of containers")
        node.destroy_container(c1)
        self.assertTrue(len(node.all_containers()) == 1, "List of containers on a node was wrong after destroying one")
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
        self.assertTrue(c2.all_tunnels()[0] == t1, "List of tunnels on container did not contain right one")
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

        # permissions
        c1 = node.spawn(TfTest.image, no_image_check=True)
        c1.allow_connection_from(c2)
        self.assertTrue(len(c1.all_allowed_connections()) == 1, "Did not add to the list of permissions")
        self.assertTrue(c2 in c1.all_allowed_connections(), "Did not add the correct container to the permissions")
        c1.disallow_connection_from(c2)
        self.assertTrue(len(c1.all_allowed_connections()) == 0, "List of permissions did not shrink again")

        # processes
        p1 = c1.spawn_process('sleep inf')
        self.assertTrue(len(c1.all_processes()) == 1, "List of processes was wrong")
        self.assertTrue(p1 in c1.all_processes(), "Did not add the correct process to the process list")
        p2 = c1.spawn_process('sleep inf')
        self.assertTrue(len(c1.all_processes()) == 2, "List of processes did not grow")
        self.assertTrue(p1 in c1.all_processes(), "Lost first process from list of processes")
        self.assertTrue(p2 in c1.all_processes(), "New process was not added to list of processes")
        c1.destroy_process(p2)
        self.assertTrue(len(c1.all_processes()) == 1, "List of processes did not shrink")
        self.assertTrue(p1 in c1.all_processes(), "Removed the wrong process from the process list")

        # do we know the process is dead?
        try:
            p2.wait_until_complete()
        except ValueError:
            self.assertTrue(True)

    def test_multiple_connect(self):
        # should be banned by the geneva convention
        locs = [Location() for n in range(0, 5)]
        nodes = [loc.best_node() for loc in locs]
        containers = [node.spawn(TfTest.image, no_image_check=True) for node in nodes]
        self.assertTrue(True)

    def test_file_handling(self):
        # tests raising exceptions, too
        container = TfTest.location.best_node().spawn(TfTest.image, no_image_check=True)

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

        # a non-existent file
        try:
            print(container.fetch('nothere'))
            self.assertTrue(False, 'Trying to fetch a non-existent file did not throw an excepton')
        except ValueError:
            self.assertTrue(True)

        # exists but is a directory
        try:
            print(container.fetch('/usr'))
            self.assertTrue(False, 'Trying to fetch a directory did not throw an excepton')
        except ValueError as e:
            self.assertTrue(True)

    def test_spawn_process(self):
        container = TfTest.location.best_node().spawn(TfTest.image, no_image_check=True)

        # test command styles
        r1 = container.spawn_process('echo "Hello World"').wait_until_complete()
        self.assertTrue(r1 == b'Hello World\r\n')
        r2 = container.spawn_process(['echo', 'Hello World']).wait_until_complete()
        self.assertTrue(r2 == b'Hello World\r\n')

    def test_callbacks(self):
        self.test_data = b''
        self.terminated_process = None

        def test_data_callback(obj, data):
            self.test_data += data

        def test_termination_callback(obj):
            self.terminated_process = obj

        node = TfTest.location.best_node()
        container = node.spawn(TfTest.image, no_image_check=True)

        # a long lived process test asynchronous results
        long_process = container.spawn_process('vmstat 1', data_callback=test_data_callback)

        # a short process tests termination
        short_process = container.spawn_process('true', termination_callback=test_termination_callback)
        short_process.wait_until_complete()
        time.sleep(1)
        self.assertTrue(self.terminated_process is short_process, 'Termination callbacks not working')

        # worked asynchronously
        time.sleep(2.5)
        snapshot = bytes(self.test_data)
        lines = snapshot.count(b'\n')
        self.assertTrue(lines == 6, 'Data callbacks not working')  # six lines of output

        # destroys
        container.destroy_process(long_process)
        time.sleep(2)  # give it a chance to go wrong
        destroyed_lines = self.test_data.count(b'\n')
        self.assertEqual(lines, destroyed_lines, 'Destroying a long running process didn\'t work')

        # works for a shell
        self.test_data = b''
        shell = container.spawn_shell(data_callback=test_data_callback,
                                      termination_callback=test_termination_callback)
        shell.stdin(b'ps faxu\n')
        time.sleep(1)
        container.destroy_process(shell)
        self.assertTrue(b'BrandZ' in self.test_data and b'Linux' in self.test_data, "Did not apparently shell in")
        self.assertTrue(self.terminated_process is shell, 'Shell did not call termination callback')

        # being informed of the termination of a process because it was inside a container that was destroyed
        proc = container.spawn_process('sleep inf', termination_callback=test_termination_callback)
        time.sleep(1)
        node.destroy_container(container)
        time.sleep(1)
        self.assertTrue(self.terminated_process == proc, 'Destroyed process (due to container) callback not working')

    def test_process_interact(self):
        self.bash_data = b''

        def test_interactive_callback(obj, data):
            self.bash_data += data

        container = TfTest.location.best_node().spawn(TfTest.image, no_image_check=True)
        bash = container.spawn_process('/bin/bash', data_callback=test_interactive_callback)

        bash.stdin('true\n'.encode())
        time.sleep(1)
        self.assertTrue(self.bash_data == b'true\r\n', "Did not return echoed input from remote process")
        self.bash_data = b''
        bash.stdin('date\n'.encode())
        time.sleep(1)
        self.assertTrue(self.bash_data.count(b'\r\n'), "Asynchronous return did not have two lines")
        century = self.bash_data[-6:-4]
        self.assertTrue(century == b'19' or century == b'20', "Asynchronous return did not apparently send date")

        self.bash_data = b''
        captured = bash.stdin('date\n'.encode(), return_reply=True)
        self.assertTrue(captured == self.bash_data, "Synchronous reply did not return the same as callback")
        captured = bash.stdin('date\n'.encode(), return_reply=True, drop_echo=True)
        self.assertTrue(captured.count(b'\r\n') == 1, "Synchronous reply did not drop echo")

    def test_tunnels_http(self):
        container = TfTest.location.best_node().spawn(TfTest.image, no_image_check=True)

        # creating a tunnel after http 200
        tnl = container.wait_http_200()
        reply = None
        try:
            reply = subprocess.check_output(['curl', 'http://127.0.0.1:' + str(tnl.localport())])
        except BaseException as e:
            self.assertTrue(False, 'Running curl against the tunnel threw an exception: ' + str(e))
        self.assertTrue(TfTest.root_reply_contains.encode() in reply, 'Did not get the expected reply from container')

        # seeing if it was logged
        logs = container.logs()
        self.assertTrue(len(logs) != 0, 'Container logs were blank')
        self.assertTrue('curl/' in logs[len(logs)-1]['log'], 'The request from curl didn\'t show up in server logs')

    def test_contain_loop(self):
        bad_container, good_container = self._two_containers()

        # eat cpu
        processes = []
        for n in range(0, 10):
            processes.append(bad_container.spawn_process('dd if=/dev/zero of=/dev/null'))
        time.sleep(10)
        ps_result = good_container.spawn_process('ps ax').wait_until_complete()
        self.assertTrue(TfTest.launched_process in ps_result.decode('ascii'))

    def test_contain_cat(self):
        bad_container, good_container = self._two_containers()

        # bad container attacks the file system
        processes = []
        for n in range(0,10):
            processes.append(bad_container.spawn_process('cat /dev/zero > zeroes' + str(n)))
        time.sleep(10)
        ps_result = good_container.spawn_process('ps ax').wait_until_complete()
        self.assertTrue(TfTest.launched_process in ps_result.decode('ascii'))
        bad_container.spawn_process('rm zeroes*')

    def test_contain_fork_bomb(self):
        bad_container, good_container = self._two_containers()

        # bad container runs a fork bomb
        bad_container.spawn_process(':(){ :|: & };:')
        time.sleep(10)
        ps_result = good_container.spawn_process('ps ax').wait_until_complete()
        self.assertTrue(TfTest.launched_process in ps_result.decode('ascii'))

    def _two_containers(self):
        node = TfTest.location.best_node()
        bad_container = node.spawn(TfTest.image, no_image_check=True)
        good_container = node.spawn(TfTest.image, no_image_check=True)
        return bad_container, good_container


if __name__ == '__main__':
    main()
