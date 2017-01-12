"""Copyright (c) 2017 David Preece, All rights reserved.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

from setuptools import setup
setup(name='tfnz',
      version='0.9.1',
      author='David Preece',
      author_email='davep@polymath.tech',
      url='https://20ft.nz',
      license='BSD',
      packages=['tfnz'],
      install_requires=['pyzmq', 'libnacl', 'py3dns', 'requests', 'shortuuid'],
      description='SDK for 20ft.nz',
      long_description="The SDK for the 20ft.nz container infrastructure. " +
                       "This package contains the SDK, the 'tf' command line tool and man page. " +
                       "Main documentation is at http://docs.20ft.nz",
      keywords='container containers docker orchestration 20ft 20ft.nz',
      classifiers=[
            'Development Status :: 4 - Beta',
            'Intended Audience :: Developers',
            'Intended Audience :: Information Technology',
            'Intended Audience :: System Administrators',
            'License :: OSI Approved :: BSD License',
            'Natural Language :: English',
            'Operating System :: MacOS :: MacOS X',
            'Topic :: Software Development :: Testing',
            'Topic :: System :: Software Distribution',
            'Programming Language :: Python :: 3.4',
            'Programming Language :: Python :: 3.5',
            'Programming Language :: Python :: 3.6'
      ],
      entry_points={
            'console_scripts': ['tf = tfnz.tf:main']
      },
      data_files=[
            ('/usr/local/share/man/man1', ['tf.1'])
      ]
      )

