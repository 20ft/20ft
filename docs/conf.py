# -*- coding: utf-8 -*-
extensions = ['sphinx.ext.autodoc']
templates_path = ['_templates']
source_suffix = '.rst'

master_doc = 'index'
project = u'20ft'
copyright = u'2017, David Preece'
author = u'David Preece'

version = u'0.1'
release = u'0.1'

# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
# pip install sphinx-py3doc-enhanced-theme
import sphinx_py3doc_enhanced_theme
html_theme = 'sphinx_py3doc_enhanced_theme'
html_theme_path = [sphinx_py3doc_enhanced_theme.get_html_theme_path()]
html_theme_options = {
    'githuburl': 'https://github.com/rantydave/tfnz/',
    'bodyfont': '"Lucida Grande",Arial,sans-serif',
    'headfont': '"Lucida Grande",Arial,sans-serif',
    'codefont': 'monospace,sans-serif',
    'linkcolor': '#0072AA',
    'visitedlinkcolor': '#6363bb',
    'extrastyling': False,
}
pygments_style = 'friendly'
html_static_path = ['_static']

htmlhelp_basename = '20ftdoc'

# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
(master_doc, '20ft', u'20ft Documentation',
 [author], 1)
]
