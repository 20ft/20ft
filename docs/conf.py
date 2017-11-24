import sphinx_rtd_theme

extensions = ['sphinx.ext.autodoc']
templates_path = ['_templates']
source_suffix = '.rst'

master_doc = 'index'
project = u'20ft'
copyright = u'2016-2017, David Preece'
author = u'David Preece'

version = u'1.1.7'
release = u'1.1.7'

html_theme = 'sphinx_rtd_theme'
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', '.git', '.hg']
html_static_path = ['_static']
pygments_style = 'friendly'
autodoc_member_order = 'bysource'
