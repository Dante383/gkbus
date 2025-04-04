import os
import sys

sys.path.insert(0, os.path.abspath('..')) #/../gkbus/'))

from gkbus import __version__

# Configuration file for the Sphinx documentation builder.

# -- General configuration

extensions = [
#    'sphinx.ext.duration',
 #   'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
	'sphinx.ext.intersphinx',
	'sphinx.ext.todo',
	'sphinx.ext.viewcode',
    'sphinx.ext.autosummary',
]

#intersphinx_disabled_domains = ['std']

templates_path = ['_templates']

source_suffix = '.rst'

project = 'gkbus'
copyright = '2025, Dante'
author = 'Dante'

release = __version__
version = __version__

language = 'en'

pygments_style = 'sphinx'

autosummary_generate = True

nitpick_ignore = [('py:class', 'type')] # @todo take a closer look

# -- Options for HTML output

html_theme = 'sphinx_rtd_theme'

html_theme_options = {

}

#html_static_path = ['_static']

html_use_smartypants = False

html_show_sphinx = False

# -- Options for EPUB output
epub_show_urls = 'footnote'

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
