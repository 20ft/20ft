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

import requests
import os
import signal
from time import sleep
from unittest import TestCase, main
from os.path import expanduser
from subprocess import check_output, CalledProcessError, Popen, run, DEVNULL, PIPE


class CliTest(TestCase):
    tf = 'tfnz '

    @staticmethod
    def bin(po=None):
        if po is not None:
            pgid = os.getpgid(po.pid)  # alpine needs you to start a new session AND nuke the whole group
            os.killpg(pgid, signal.SIGTERM)
            po.wait()
        try:
            all = check_output('ls /tmp/tf-*', shell=True, start_new_session=True)
        except CalledProcessError:  # no tf-whatever files
            return
        for instance in all.split():
            docker_id = ''
            with open(instance) as f:
                docker_id = f.read()
            run('rm ' + instance.decode(), shell=True, start_new_session=True)
            try:
                run('docker kill ' + docker_id, stderr=DEVNULL, stdout=DEVNULL, shell=True, start_new_session=True)
            except CalledProcessError:
                pass

    def test_ends(self):
        try:
            out = run(CliTest.tf + 'tfnz/ends_test', shell=True, start_new_session=True, stderr=PIPE)
            self.assertTrue(b"Container is running" in out.stderr)
            self.assertTrue(b"Container has exited and/or been destroyed" in out.stderr)
            self.assertTrue(b"Disconnecting" in out.stderr)
        finally:
            CliTest.bin()

    def test_verbose(self):
        try:
            out = run(CliTest.tf + '-v alpine true', shell=True, start_new_session=True, stderr=PIPE)
            self.assertTrue(b"Message loop started" in out.stderr)
        finally:
            CliTest.bin()

    def test_quiet(self):
        try:
            out = run(CliTest.tf + '-q alpine true', shell=True, start_new_session=True, stderr=PIPE)
            self.assertTrue(len(out.stderr) == 0)
        finally:
            CliTest.bin()

    def test_portmap(self):
        try:
            po = Popen(CliTest.tf + '-p 8080:80 nginx', shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue("Welcome to nginx!" in reply.text)
        finally:
            CliTest.bin(po)

    def test_environment(self):
        try:
            po = Popen(CliTest.tf + '-e TEST=environment -e VAR=iable  -p 8080:80 tfnz/env_test',
                       shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue("TEST=environment" in reply.text)
            self.assertTrue("VAR=iable" in reply.text)
        finally:
            CliTest.bin(po)

    def test_preboot(self):
        try:
            po = Popen(CliTest.tf + '-f cli_test.py:/usr/share/nginx/html/index.html -p 8080:80 nginx',
                       shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue("test_preboot(self)" in reply.text)
        finally:
            CliTest.bin(po)

    def test_mount_volume(self):
        po = None
        try:
            # creating with a cli tag
            try:
                uuid = check_output(CliVolsTest.tfvolumes + 'create with_cli_tag', shell=True).decode().rstrip('\r\n')
            except CalledProcessError as e:
                run(CliVolsTest.tfvolumes + "destroy with_cli_tag", shell=True)
                uuid = check_output(CliVolsTest.tfvolumes + 'create with_cli_tag', shell=True).decode().rstrip('\r\n')
            print("Vol uuid = " + str(uuid))

            # mount using the cli tag
            print('\n' + CliTest.tf + '-s -m with_cli_tag:/usr/share/nginx/html/ -p 8080:80 nginx')
            po = Popen(CliTest.tf + '-s -m with_cli_tag:/usr/share/nginx/html/ -p 8080:80 nginx',
                       shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue(reply.status_code == 403)  # initially nothing in the volume

            # upload a file with sftp
            run('echo "put tfnz.1 /usr/share/nginx/html/index.html" | sftp -P 2222 root@localhost',
                shell=True, start_new_session=True)
            sleep(1)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue(".TH TFNZ(1)" in reply.text)
            CliTest.bin(po)

            # mount using tag:uuid (in another container)
            print('\n' + CliTest.tf + '-m %s:/usr/share/nginx/html/ -p 8080:80 nginx' % uuid)
            po = Popen(CliTest.tf + '-m %s:/usr/share/nginx/html/ -p 8080:80 nginx' % uuid,
                       shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue(".TH TFNZ(1)" in reply.text)
            CliTest.bin(po)

            # mount with just uuid
            print('\n' + CliTest.tf + '-m %s:/usr/share/nginx/html/ -p 8080:80 nginx' % uuid.split(':')[0])
            po = Popen(CliTest.tf + '-m %s:/usr/share/nginx/html/ -p 8080:80 nginx' % uuid.split(':')[0],
                       shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue(".TH TFNZ(1)" in reply.text)
            CliTest.bin(po)

            # mount with just tag
            print('\n' + CliTest.tf + '-m %s:/usr/share/nginx/html/ -p 8080:80 nginx' % uuid.split(':')[1])
            po = Popen(CliTest.tf + '-m %s:/usr/share/nginx/html/ -p 8080:80 nginx' % uuid.split(':')[1],
                       shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://127.0.0.1:8080')
            self.assertTrue(".TH TFNZ(1)" in reply.text)
        finally:
            CliTest.bin(po)
            run(CliVolsTest.tfvolumes + 'destroy with_cli_tag', shell=True)

    def test_start_script(self):  # also tests ssh
        try:
            with open("new_script.sh", 'w') as f:
                f.write('echo "I did this!" > /test ; /bin/sleep 1000')
            po = Popen(CliTest.tf + '-s -f new_script.sh:/new_script.sh alpine sh /new_script.sh',
                       shell=True, start_new_session=True)
            sleep(5)
            out = check_output('ssh -p 2222 root@localhost cat /test',
                               shell=True, start_new_session=True)
            self.assertTrue(b"I did this!" in out)
        finally:
            run('rm new_script.sh', shell=True, start_new_session=True)
            CliTest.bin(po)

    def test_web_host(self):
        try:
            po = Popen(CliTest.tf + '-w cli.test.sydney.20ft.nz nginx', shell=True, start_new_session=True)
            sleep(5)
            reply = requests.get('http://cli.test.sydney.20ft.nz')
            self.assertTrue("Welcome to nginx!" in reply.text)
        finally:
            CliTest.bin(po)

    def test_sleep(self):
        try:
            po = Popen(CliTest.tf + '-z -s alpine', shell=True, start_new_session=True)
            sleep(5)
            out = check_output('ssh -p 2222 root@localhost uname', shell=True, start_new_session=True)
            self.assertTrue(b"Linux" in out)
        finally:
            CliTest.bin(po)


class CliVolsTest(TestCase):
    tfvolumes = 'tfvolumes '

    def test_blank(self):
        try:
            out = check_output(CliVolsTest.tfvolumes, shell=True, start_new_session=True)
            self.assertTrue(b"{list,create,destroy}" in out)
        finally:
            CliTest.bin()

    def test_destroy_missing(self):
        try:
            run(CliVolsTest.tfvolumes + "destroy", shell=True, stderr=DEVNULL, start_new_session=True)
        except CalledProcessError as e:
            self.assertTrue(b"the following arguments are required: uuid" in e.output)
            self.assertTrue(e.returncode != 0)
        finally:
            CliTest.bin()

    def test_crud(self):
        try:
            uuid = check_output(CliVolsTest.tfvolumes + 'create', shell=True).rstrip(b'\r\n')
            self.assertTrue(len(uuid) != 0)
            all = check_output(CliVolsTest.tfvolumes + 'list', shell=True, start_new_session=True)
            self.assertTrue(uuid in all)
            destroyed = check_output(CliVolsTest.tfvolumes + 'destroy ' + uuid.decode(),
                                     shell=True, start_new_session=True)
            self.assertTrue(len(uuid) != 0)
        finally:
            CliTest.bin()

    def test_crud_tagged(self):
        try:
            uuid_tag = check_output(CliVolsTest.tfvolumes + 'create test_crud_tagged',
                                    shell=True, start_new_session=True).rstrip(b'\r\n')
            self.assertTrue(b'error' not in uuid_tag)
            all = check_output(CliVolsTest.tfvolumes + 'list', shell=True, start_new_session=True)
            self.assertTrue(uuid_tag in all)
            destroyed = check_output(CliVolsTest.tfvolumes + 'destroy ' + uuid_tag.decode(),
                                     shell=True, start_new_session=True)
            self.assertTrue(b'error' not in destroyed)
            all = check_output(CliVolsTest.tfvolumes + 'list',
                               shell=True, start_new_session=True)
            self.assertTrue(uuid_tag not in all)
        finally:
            CliTest.bin()


class CliAcctbakTest(TestCase):
    tfacctbak = 'tfacctbak'

    def test_acctbak(self):
        with open(expanduser("~/.20ft/default_location")) as f:
            def_loc = f.read().rstrip('\r\n')
        with open(expanduser("~/.20ft/") + def_loc) as f:
            priv = f.read().encode().rstrip(b'\r\n')
        with open(expanduser("~/.20ft/%s.pub") % def_loc) as f:
            pub = f.read().encode().rstrip(b'\r\n')
        def_loc = def_loc.encode()
        out = check_output(CliAcctbakTest.tfacctbak, shell=True, start_new_session=True)
        self.assertTrue(b"cat > ~/.20ft/default_location" in out)
        self.assertTrue(b"cat > ~/.20ft/" + def_loc in out)
        self.assertTrue(b"cat > ~/.20ft/" + def_loc + b".pub" in out)
        self.assertTrue(def_loc in out)
        self.assertTrue(pub in out)
        self.assertTrue(priv in out)


if __name__ == '__main__':
    main()
