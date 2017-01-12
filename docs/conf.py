# -*- coding: utf-8 -*-
# pip install sphinxcontrib-googleanalytics
# needs to be installed into python 2!!


extensions = ['sphinx.ext.autodoc', 'sphinxcontrib.googleanalytics']
templates_path = ['_templates']
source_suffix = '.rst'

master_doc = 'index'
project = u'20ft'
copyright = u'2016-2017, David Preece'
author = u'David Preece'
googleanalytics_id = 'UA-301585-19'

version = u'0.9'
release = u'0.9'

html_theme = "sphinx_rtd_theme"
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', '.git', '.hg']
html_static_path = ['_static']
pygments_style = 'friendly'
