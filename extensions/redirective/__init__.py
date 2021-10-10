from typing import Dict, Any, List, Tuple

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

# Sphinx logger
logger = logging.getLogger(__name__)


class RedirectiveNode(nodes.General, nodes.Element):
    redirect_list: List[str]

    def __init__(self, redirects: List[str]):
        super().__init__()
        self.redirect_list = redirects.copy()

    def astext(self) -> str:
        return ','.join(self.redirect_list)

    def get_list(self) -> List[str]:
        return self.redirect_list


class Redirective(SphinxDirective):
    has_content = True

    def run(self) -> List[nodes.Node]:
        redirects: List[str] = list()
        for line in self.content.data:
            redirects.append('%s' % line)

        return [RedirectiveNode(redirects)]


class DoctreeWalker(nodes.SparseNodeVisitor):
    section_redirects: Dict[str, List[str]]

    def __init__(self, document: nodes.document):
        super().__init__(document)
        self.section_redirects = dict()

    def visit_section(self, node: nodes.section):
        # look for redirective nodes; remove them when we're done
        redirects: List[str] = list()
        for child in node.children:
            if isinstance(child, RedirectiveNode):
                redirects.append(child.astext())
                child.replace_self([])
        if len(redirects) > 0:
            # get section id
            section_id: str = '??'
            for att in node.attlist():
                if att[0] == 'ids':
                    section_id = att[1][0]
            # logger.info('section: %s' % section_id)
            # for redirect in redirects:
            #     logger.info(">> redirective: %s" % redirect)
            self.section_redirects[section_id] = redirects

    def unknown_visit(self, node: nodes.Node) -> Any:
        raise nodes.SkipNode

    def get_redirects(self) -> Dict[str, List[str]]:
        return self.section_redirects


def setup(app: Sphinx) -> Dict[str, Any]:
    """
    Sphinx extension setup function.

    :param app: The Sphinx Application instance
    :return: A dict of Sphinx extension options
    """
    app.add_directive('redirective', Redirective)
    app.add_node(RedirectiveNode)
    app.connect('env-purge-doc', env_purge_doc)
    app.connect('env-merge-info', env_merge_info)
    app.connect('html-collect-pages', html_collect_pages)
    app.connect('doctree-resolved', doctree_resolved)
    return {
        'version': '0.1',
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
    logger.debug('env_purge_doc: docname=%s' % docname)
    if hasattr(env, 'redirective_redirects'):
        redirects: Dict[str, List[str]] = env.redirective_redirects
        if docname in redirects:
            logger.debug('env_purge_doc: redirects contains %s; removing it' % docname)
            redirects.pop(docname)


def env_merge_info(app: Sphinx, env: BuildEnvironment, docnames: List[str], other: BuildEnvironment) -> None:
    """
    Merge collected document names from parallel readers (workers) into the master Sphinx environment.
    This function is called when the Sphinx `env-merge-info` event is fired.

    :param app: The Sphinx Application instance
    :param env: The master Sphinx BuildEnvironment
    :param docnames: A list of the document names to merge
    :param other: The Sphinx BuildEnvironment from the reader worker
    """
    redirects: Dict[str, List[str]] = dict()
    if not hasattr(env, 'redirective_redirects'):
        env.redirective_redirects = redirects
    else:
        redirects = env.redirective_redirects
    # Add any links that were present in the reader worker's environment
    if hasattr(other, 'redirective_redirects'):
        other_redirects: Dict[str, List[str]] = other.redirective_redirects
        for linkKey in other_redirects:
            if linkKey in env.redirective_redirects:
                env.redirective_redirects[linkKey].extend(other_redirects[linkKey])
            else:
                env.redirective_redirects[linkKey] = other_redirects[linkKey]


def html_collect_pages(app: Sphinx) -> List[Tuple[str, Dict[str, Any], str]]:
    """
    Collect the redirect page files.

    :param app: The Sphinx Application instance
    :return: A list of redirect pages to create
    """
    redirect_pages: List[Tuple[str, Dict[str, Any], str]] = list()
    if hasattr(app.env, 'redirective_redirects'):
        redirs: Dict[str, List[str]] = app.env.redirective_redirects
        for redir_from in redirs:
            logger.info('%s -> %s' % (redir_from, ','.join(redirs[redir_from])))
            for redir_to in redirs[redir_from]:
                redirect_pages.append((redir_from,
                                       {
                                           'title': 'redirecting...',
                                           'to_uri': redir_to,
                                       },
                                       'redirective.html'))
    return redirect_pages


def doctree_resolved(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    if docname != 'configure/configuration-settings':
        return
    walker: DoctreeWalker = DoctreeWalker(doctree)
    doctree.walk(walker)
    section_redirects: Dict[str, List[str]] = walker.get_redirects()
    if len(section_redirects) == 0:
        return
    redirects: Dict[str, List[str]] = dict()
    if hasattr(app.env, 'redirective_redirects'):
        redirects = app.env.redirective_redirects
    else:
        app.env.redirective_redirects = redirects
    for section_id in section_redirects:
        # from: section_redirects[section_id]...
        for sec_redir in section_redirects[section_id]:
            redirect_from = sec_redir
            # to: docname + '#' + section_id
            redirect_to = '%s#%s' % (docname, section_id)
            if redirect_from in redirects:
                redirects[redirect_from].append(redirect_to)
            else:
                redirects[redirect_from] = [redirect_to]

