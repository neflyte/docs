from typing import Any, Dict

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment
from sphinx.util import logging

# Sphinx logger
logger = logging.getLogger(__name__)
searchv2_env_key = "searchv2"


def setup(app: Sphinx) -> Dict[str, Any]:
    """
    Sphinx extension setup function.
    It adds config values and connects Sphinx events to the sitemap builder.

    :param app: The Sphinx Application instance
    :return: A dict of Sphinx extension options
    """
    app.connect("env-purge-doc", env_purge_doc)
    return {
        'version': '0.1',
        # Enable parallel reading and writing
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }


def env_purge_doc(app: Sphinx, env: BuildEnvironment, docname: str) -> None:
    """
    Purge an existing document from the pickled document list.
    This function is called when the Sphinx `env-purge-doc` event is fired.

    :param app: The Sphinx instance; unused
    :param env: The Sphinx BuildEnvironment
    :param docname: The name of the document to purge
    """
    if hasattr(env, searchv2_env_key):
        searchenv: Dict[str, Any] = getattr(env, searchv2_env_key)
        if docname in searchenv:
            logger.verbose(
                "env_purge_doc: redirects contains %s; removing it" % docname
            )
            searchenv.pop(docname)


def doctree_resolved(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    """
    Walk the doctree and add to the index

    :param app: The Sphinx application instance
    :param doctree: The resolved doctree
    :param docname: The name of the document
    :return:
    """


    return

