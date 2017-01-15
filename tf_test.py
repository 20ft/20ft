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
from tfnz.container import Container, description


class TfTest(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.image = 'nginx'
        cls.launched_process = b'nginx: worker process'
        cls.root_reply_contains = b'<title>Welcome to nginx!</title>'
        cls.acceptable_boot_time = 10
        cls.location = Location(debug_log=False)
        cls.location.ensure_image_uploaded(cls.image)

    def test_node(self):
        nodes = TfTest.location.ranked_nodes()
        self.assertTrue(len(nodes) > 0, 'No nodes are live, testing is not going to go well')
        if len(nodes) == 0:
            return
        self.assertTrue(nodes[0].parent() == TfTest.location, 'Node has the wrong parent')
        if len(nodes) == 1:
            return
        self.assertTrue(nodes[0].stats['memory'] > nodes[1].stats['memory'], 'Node ranking is wrong')
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
            running = TfTest.launched_process in ps_result
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
        self.assertTrue(TfTest.launched_process not in ps_result, 'Asked for an asleep container but it started anyway')
        self.assertTrue(b'sleep' in ps_result, 'The sleep command does not appear to be running')

    def test_spawn_preboot(self):
        # write configuration files before we boot
        preboot = {'/usr/share/nginx/html/index.html': 'Hello World!'}
        container = TfTest.location.best_node().spawn(TfTest.image, pre_boot_files=preboot, no_image_check=True)
        self.assertTrue(b'Hello World!' in container.fetch('/usr/share/nginx/html/index.html'))

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

    def test_callbacks(self):
        self.vmstat_data = b''
        self.terminated_process = None

        def test_vmstat_callback(obj, data):
            self.vmstat_data += data

        def termination_callback(obj):
            self.terminated_process = obj

        container = TfTest.location.best_node().spawn(TfTest.image, no_image_check=True)

        # a long lived process test asynchronous results
        long_process = container.spawn_process('vmstat 1', data_callback=test_vmstat_callback)

        # a short process tests termination
        short_process = container.spawn_process('true', termination_callback=termination_callback)
        short_process.wait_until_complete()
        time.sleep(1)
        self.assertTrue(self.terminated_process is short_process, 'Termination callbacks not working')

        # worked asynchronously
        time.sleep(2)
        lines = self.vmstat_data.count(b'\n')
        self.assertTrue(lines == 5 or lines == 6, 'Data callbacks not working')  # five lines of output

        # destroys
        long_process.destroy()
        time.sleep(2)  # give it a chance to go wrong
        destroyed_lines = self.vmstat_data.count(b'\n')
        self.assertEqual(lines, destroyed_lines, 'Destroying a long running process didn\'t work')

        # being informed of the termination of a process because it was inside a container that was destroyed
        proc = container.spawn_process('sleep 100', termination_callback=termination_callback)
        time.sleep(3)
        container.destroy()
        time.sleep(3)
        self.assertTrue(self.terminated_process == proc, 'Destroyed process (due to container) callback not working')

    def test_tunnels_http(self):
        container = TfTest.location.best_node().spawn(TfTest.image, no_image_check=True)

        # creating a tunnel after http 200
        tnl = container.wait_http_200()
        reply = None
        try:
            reply = subprocess.check_output(['curl', 'http://127.0.0.1:' + str(tnl.localport)],
                                            stderr=subprocess.DEVNULL)
        except BaseException as e:
            self.assertTrue(False, 'Running curl against the tunnel threw an exception: ' + str(e))
        self.assertTrue(TfTest.root_reply_contains in reply, 'Did not get the expected reply from container')

        # seeing if it was logged
        logs = container.logs()
        self.assertTrue(len(logs) != 0, 'Container logs were blank')
        self.assertTrue('curl/' in logs[len(logs)-1]['log'], 'The request from curl didn\'t show up in server logs')

    def test_resource_management(self):
        # can the "good" container get work done while the "bad" container is being bad?
        node = TfTest.location.best_node()  # won't interfere at all if they're not on the same node
        bad_container = node.spawn(TfTest.image, no_image_check=True)
        good_container = node.spawn(TfTest.image, no_image_check=True)

        # eat cpu
        processes = []
        for n in range(0, 10):
            processes.append(bad_container.spawn_process('dd if=/dev/zero of=/dev/null'))
        time.sleep(10)
        ps_result = good_container.spawn_process('ps ax').wait_until_complete()
        self.assertTrue(TfTest.launched_process in ps_result)
        for process in processes:
            process.destroy()

        # death cat
        processes = []
        for n in range(0,10):
            processes.append(bad_container.spawn_process('cat /dev/zero > zeroes' + str(n)))
        time.sleep(10)
        ps_result = good_container.spawn_process('ps ax').wait_until_complete()
        self.assertTrue(TfTest.launched_process in ps_result)
        for process in processes:
            process.destroy()
        bad_container.spawn_process('rm zeroes*')

        # fork bomb
        bad_container.spawn_process(':(){ :|: & };:')
        time.sleep(10)
        ps_result = good_container.spawn_process('ps ax').wait_until_complete()
        self.assertTrue(TfTest.launched_process in ps_result)


if __name__ == '__main__':
    main()
